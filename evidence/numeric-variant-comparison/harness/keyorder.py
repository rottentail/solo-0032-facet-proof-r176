"""Companion scenario: identical geometry, swapped placement keys.

Two assemblies contain the same two coplanar quads, the same pigment, and the
same lens. Only the placement keys differ, and keys decide object numbering
because the baseline sorts placements by key. The object channel can therefore
change owner on hundreds of pixels while color and depth stay identical.

This scenario shows a blind spot in the service's own comparison endpoint: it
reports color, silhouette, and depth differences but never reads the object
channel, so it can call two plates "the same" while they disagree about which
part owns a pixel. It is evidence about what each channel can prove, not a
verdict on any build.
"""
import struct

import compare
import font
import pngdiff
import sheet


def run(call, spec):
    mesh_id = call("POST", "meshes", spec["mesh"])["id"]
    pigment_id = call("POST", "pigments", spec["pigment"])["id"]
    plates = []
    for variant in spec["variants"]:
        assembly = call("POST", "assemblies", {"name": spec["id"] + "-" + variant["label"],
                                               "lens": spec["lens"],
                                               "illumination": spec["illumination"]})
        placements = [{"key": placement["key"], "mesh_id": mesh_id, "pigment_id": pigment_id,
                       "transform": placement.get("transform", {})}
                      for placement in variant["placements"]]
        assembly = call("PUT", "assemblies/" + assembly["id"],
                        {"revision": 1, "placements": placements})
        seal = call("POST", "assemblies/" + assembly["id"] + "/seal", {"revision": 2})
        request = dict(spec["request"])
        request["key"] = spec["request"]["key"] + "-" + variant["label"]
        call("POST", "seals/" + seal["id"] + "/exposures", request)
        plate = call("POST", "worker/step")["plate"]
        channels = {name: call("GET", "plates/" + plate["id"] + "/passes/" + name)[0]
                    for name in ("color.rgb", "depth.f32", "object.u32",
                                 "color.png", "depth.png", "object.png")}
        plates.append({"label": variant["label"], "seal": seal, "plate": plate,
                       "channels": channels})
    return plates


def reading(plates, spec):
    width = spec["request"]["width"]
    height = spec["request"]["height"]
    left, right = plates
    return {
        "scenario": spec["id"],
        "title": spec["title"],
        "question": spec["question"],
        "left": left["label"],
        "right": right["label"],
        "left_objects": {key: value["key"] for key, value in left["plate"]["payload"]["objects"].items()},
        "right_objects": {key: value["key"] for key, value in right["plate"]["payload"]["objects"].items()},
        "left_visual_hash": left["plate"]["payload"]["visual_hash"],
        "right_visual_hash": right["plate"]["payload"]["visual_hash"],
        "seal_hashes_differ": left["plate"]["payload"]["seal_hash"] != right["plate"]["payload"]["seal_hash"],
        "channel_compare": compare.classify(left["channels"], right["channels"], width, height),
        "depth_delta": compare.depth_delta(left["channels"], right["channels"], width, height),
        "ownership_transitions": {"%d->%d" % pair: count for pair, count in
                                  compare.ownership_transitions(
                                      left["channels"], right["channels"], width, height).items()},
        "note": ("Color and depth are effectively identical; the object channel moved owner. "
                 "The service comparison endpoint below does not read the object channel."),
    }


def service_comparison(call, plates):
    left, right = plates
    return call("POST", "comparisons", {"left": left["plate"]["id"], "right": right["plate"]["id"]})["payload"]


def sheet_png(spec, plates, reading_value, comparison, width, height):
    left, right = plates
    panels = [
        {"label": "1 %s COLOR" % left["label"].upper(),
         "image": (width, height, left["channels"]["color.rgb"])},
        {"label": "2 %s COLOR" % right["label"].upper(),
         "image": (width, height, right["channels"]["color.rgb"])},
        {"label": "3 OWNERSHIP CHANGE LEFT -> RIGHT",
         "image": (width, height, pngdiff.ownership_map_rgb(
             width, height, left["channels"]["object.u32"], right["channels"]["object.u32"]))},
        {"label": "4 COLOR DELTA LEFT -> RIGHT",
         "image": (width, height, pngdiff.color_delta_rgb(
             width, height, left["channels"]["color.rgb"], right["channels"]["color.rgb"]))},
        {"label": "5 DEPTH DELTA LEFT -> RIGHT",
         "image": (width, height, depth_delta_rgb(width, height,
                                                  left["channels"]["depth.f32"],
                                                  right["channels"]["depth.f32"]))},
        {"label": "6 SERVICE /COMPARISONS METRIC",
         "image": (360, 290, metric_strip(360, 290, comparison))},
    ]
    against = reading_value["channel_compare"]
    header = [
        "Same mesh, same pigment, same lens; only placement keys are swapped between the two plates.",
        "LEFT %s   RIGHT %s" % (left["label"], right["label"]),
        "CHANNELS: color-only %d px, ownership-changed %d px, depth-bit-differences %d"
        % (against["color_only"], against["ownership_changed"], against["depth_bit_differences"]),
        "SERVICE /comparisons: color_changed %d (tolerance %d), depth_changed %d, silhouette_changed %d"
        % (comparison["color_changed"], comparison["tolerance"],
           comparison["depth_changed"], comparison["silhouette_changed"]),
    ]
    legend = [
        "The point of this sheet: the service comparison reports color/depth/silhouette only.",
        "It does not read the object channel, so it cannot report ownership drift. Compare panels 3 and 6.",
        "Object numbers are assigned by sorted placement key; the mapping is in readings/key-order.json.",
    ]
    return sheet.render("KEY-ORDER OWNERSHIP - IDENTICAL GEOMETRY, SWAPPED KEYS",
                        header, panels, legend)


def depth_delta_rgb(width, height, left_depth, right_depth):
    left = struct.unpack("<%df" % (width * height), left_depth)
    right = struct.unpack("<%df" % (width * height), right_depth)
    out = bytearray(width * height * 3)
    for pixel in range(width * height):
        if left[pixel] == right[pixel]:
            value = 0
        else:
            delta = abs(left[pixel] - right[pixel])
            value = min(255, int(round(delta * 255)))
        out[pixel * 3:pixel * 3 + 3] = bytes((value, value, value))
    return bytes(out)


def metric_strip(width, height, comparison):
    """A neutral panel carrying the service metric as text, for the sheet."""
    out = bytearray(bytes((250, 251, 252)) * (width * height))
    lines = [
        "SERVICE COMPARISON RESULT",
        "",
        "COLOR_CHANGED %d" % comparison["color_changed"],
        "MEAN_CHANNEL_DELTA %.5f" % comparison["mean_channel_delta"],
        "SILHOUETTE_CHANGED %d" % comparison["silhouette_changed"],
        "DEPTH_CHANGED %d" % comparison["depth_changed"],
        "MAX_DEPTH_DELTA %.6f" % comparison["maximum_depth_delta"],
        "",
        "THERE IS NO OBJECT-",
        "CHANNEL FIELD IN THIS",
        "RESULT AT ALL.",
    ]
    y = 16
    for line in lines:
        font.draw_text(out, width, height, 14, y, line[:44], scale=1)
        y += 18
    return bytes(out)
