"""Scenario rendering and evidence-sheet composition.

Rendering runs through the service HTTP surface for the baseline plate so the
pinned plate bytes are what the service itself produced. The variant arms run
from a normalized frozen input that excludes database identifiers; the harness
asserts that the baseline arm re-rendered from that input is byte-identical to
what the service produced before it records anything.
"""
import hashlib
import math
import struct

import pngdiff
import variant
from facetproof.application import Application
from facetproof.routing import PREFIX, route_request

import job


def http(app):
    def call(method, route, data=None):
        return route_request(app, method, PREFIX + route, data)

    return call


def submit_scenario(root, spec):
    """Drive the public service routes and return the baseline plate."""
    app = Application(root)
    call = http(app)
    mesh_ids = {key: call("POST", "meshes", data)["id"] for key, data in spec["meshes"].items()}
    pigment_ids = {key: call("POST", "pigments", data)["id"] for key, data in spec["pigments"].items()}
    assembly = call("POST", "assemblies", {"name": spec["id"], "lens": spec["lens"],
                                           "illumination": spec["illumination"]})
    placements = [{"key": placement["key"],
                   "mesh_id": mesh_ids[placement["mesh"]],
                   "pigment_id": pigment_ids[placement["pigment"]],
                   "transform": placement.get("transform", {})}
                  for placement in spec["placements"]]
    assembly = call("PUT", "assemblies/" + assembly["id"], {"revision": 1, "placements": placements})
    seal = call("POST", "assemblies/" + assembly["id"] + "/seal", {"revision": 2})
    exposure = call("POST", "seals/" + seal["id"] + "/exposures", spec["request"])
    stepped = call("POST", "worker/step")
    if stepped["state"] != "succeeded":
        raise RuntimeError("scenario render failed: %s" % stepped)
    plate = stepped["plate"]
    channels = {name: call("GET", "plates/" + plate["id"] + "/passes/" + name)[0]
                for name in ("color.rgb", "depth.f32", "object.u32",
                             "color.png", "depth.png", "object.png")}
    bundle = call("GET", "plates/" + plate["id"] + "/bundle")[0]
    verification = call("POST", "plates/" + plate["id"] + "/verify")
    return {"app": app, "call": call, "mesh_ids": mesh_ids, "pigment_ids": pigment_ids,
            "assembly": assembly, "seal": seal, "exposure": exposure, "plate": plate,
            "channels": channels, "bundle": bundle, "verification": verification}


def variant_plate(frozen, arm, baseline, width, height):
    options = variant.DIAGNOSTIC_ARMS[arm]
    result = variant.render(job.frozen_job_from_input(frozen), options)
    previews = job.previews(width, height, result)
    channels = {"color.rgb": result["color.rgb"], "depth.f32": result["depth.f32"],
                "object.u32": result["object.u32"], **previews}
    return {"channels": channels, "covered_pixels": result["covered_pixels"],
            "fragments": result["fragments"], "triangles": result["triangles"],
            "options": result["options"],
            "identity_with_service": all(channels[key] == baseline["passes"][key]
                                         for key in channels)}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def render_arm_sheet(frozen, baseline, width, height, arms):
    """Compose color, ownership map and delta panels for one scenario.

    Returns PNG bytes for the sheet plus per-arm metrics. Rows are arms; the
    first row is always the service plate. Columns are:
    color, zoomed color, ownership change map, color delta against baseline.
    """
    rows = []
    for arm in arms:
        if arm == "service":
            channels = baseline["passes"]
            metrics = None
        else:
            rendered = variant_plate(frozen, arm, baseline, width, height)
            channels = rendered["channels"]
            metrics = rendered
        if arm in ("service", "baseline"):
            colors = channels["color.rgb"]
            delta = bytes(width * height * 3)
            ownership = bytes(width * height * 4)
            zoom = pngdiff.scale(*pngdiff.crop(width, colors, width // 2 - 16, height // 2 - 16,
                                               width // 2 + 16, height // 2 + 16), 4)
        else:
            colors = channels["color.rgb"]
            colors_png = decode_rgb(channels["color.png"])
            delta = max_channel_delta(colors, baseline["passes"]["color.rgb"])
            from compare import classify
            metrics = {**classify(baseline["passes"], channels, width, height)}
            metrics["covered_pixels"] = rendered["covered_pixels"]
            zoom = pngdiff.scale(*pngdiff.crop(width, colors_png, width // 2 - 16, height // 2 - 16,
                                               width // 2 + 16, height // 2 + 16), 4)
        rows.append({"arm": arm, "colors": colors, "zoom": zoom,
                     "delta": delta, "metrics": metrics})
    return rows


def max_channel_delta(a, b):
    out = bytearray(len(a))
    for index in range(len(a)):
        out[index] = abs(a[index] - b[index])
    return bytes(out)
