"""Channel comparison and objective geometry oracles.

Two kinds of comparison are kept apart on purpose.

*Cross-implementation* comparison asks where two renders differ and in which
channel. Because a final pixel's object id and depth come from the nearest
supersample while its color can average several supersamples, a color
difference at an edge need not be an ownership difference. ``classify``
therefore counts color-only, ownership-only, and combined changes separately.

*Self-consistency* asks whether the channels of one plate agree with each other:
covered pixels have finite positive depth, background pixels have infinite
depth, object ids exist in the frozen mapping, and the PNG previews decode to
the documented formulas.

Nothing here imports a renderer.
"""
import math
import struct


def unpack(channels, width, height):
    colors = [channels["color.rgb"][i * 3:i * 3 + 3] for i in range(width * height)]
    depth = list(struct.unpack("<%df" % (width * height), channels["depth.f32"]))
    ids = list(struct.unpack("<%dI" % (width * height), channels["object.u32"]))
    return colors, depth, ids


def self_consistency(channels, width, height, objects):
    colors, depth, ids = unpack(channels, width, height)
    covered = 0
    problems = {"background_with_finite_depth": 0,
                "covered_with_infinite_depth": 0,
                "covered_with_nonpositive_depth": 0,
                "unknown_object": 0,
                "nonfinite_color": 0}
    for index in range(width * height):
        object_id = ids[index]
        distance = depth[index]
        if object_id == 0:
            if distance != math.inf:
                problems["background_with_finite_depth"] += 1
            continue
        covered += 1
        if not math.isfinite(distance):
            problems["covered_with_infinite_depth"] += 1
        elif distance <= 0:
            problems["covered_with_nonpositive_depth"] += 1
        if str(object_id) not in objects:
            problems["unknown_object"] += 1
        if any(not math.isfinite(value) for value in colors[index]):
            problems["nonfinite_color"] += 1
    return {"covered_pixels": covered, "problems": problems,
            "consistent": not any(problems.values())}


def preview_consistency(channels, width, height, decode_rgb):
    """Check PNG previews against the documented formulas.

    ``decode_rgb(raw, width, height)`` must be an independent decoder, not the
    producer's. Color must equal the raw color channel exactly. Object must
    follow the published id-to-color formula. Depth must follow the published
    shade formula; this holds for plates computed in this build because the
    preview is generated from the stored float32 depth.
    """
    color = decode_rgb(channels["color.png"], width, height)
    object_png = decode_rgb(channels["object.png"], width, height)
    depth_png = decode_rgb(channels["depth.png"], width, height)
    ids = struct.unpack("<%dI" % (width * height), channels["object.u32"])
    depth = struct.unpack("<%df" % (width * height), channels["depth.f32"])
    object_mismatch = depth_mismatch = 0
    for pixel in range(width * height):
        object_id = ids[pixel]
        expected = bytes(((object_id * factor) % 255) if object_id else 0
                         for factor in (73, 151, 199))
        if object_png[pixel * 3:pixel * 3 + 3] != expected:
            object_mismatch += 1
        distance = depth[pixel]
        shade = round(255 / (1 + distance)) if math.isfinite(distance) else 0
        if depth_png[pixel * 3] != shade:
            depth_mismatch += 1
    return {"color_png_matches_raw": color == channels["color.rgb"],
            "object_png_mismatches": object_mismatch,
            "depth_png_mismatches": depth_mismatch,
            "consistent": color == channels["color.rgb"] and object_mismatch == 0 and depth_mismatch == 0}


def classify(left, right, width, height):
    """Count pixels changed in color, ownership, or both."""
    colors_a, depth_a, ids_a = unpack(left, width, height)
    colors_b, depth_b, ids_b = unpack(right, width, height)
    color_only = ownership_only = both = 0
    depth_bit_differences = 0
    coverage_gained = coverage_lost = 0
    depth_changed_finite = 0
    for index in range(width * height):
        color_changed = colors_a[index] != colors_b[index]
        ownership_changed = ids_a[index] != ids_b[index]
        if struct.pack("<f", depth_a[index]) != struct.pack("<f", depth_b[index]):
            depth_bit_differences += 1
            if math.isfinite(depth_a[index]) and math.isfinite(depth_b[index]):
                depth_changed_finite += 1
        if ids_a[index] and not ids_b[index]:
            coverage_lost += 1
        elif ids_b[index] and not ids_a[index]:
            coverage_gained += 1
        if color_changed and ownership_changed:
            both += 1
        elif color_changed:
            color_only += 1
        elif ownership_changed:
            ownership_only += 1
    return {"pixels": width * height,
            "color_changed": color_only + both,
            "ownership_changed": ownership_only + both,
            "color_only": color_only,
            "ownership_only": ownership_only,
            "both": both,
            "depth_bit_differences": depth_bit_differences,
            "depth_changed_finite": depth_changed_finite,
            "coverage_lost": coverage_lost, "coverage_gained": coverage_gained}


def ownership_transitions(left, right, width, height):
    """Map of (left id, right id) -> pixel count for pixels whose owner changed."""
    _, _, ids_a = unpack(left, width, height)
    _, _, ids_b = unpack(right, width, height)
    transitions = {}
    for index in range(width * height):
        if ids_a[index] != ids_b[index]:
            key = ids_a[index], ids_b[index]
            transitions[key] = transitions.get(key, 0) + 1
    return transitions


def changed_pixels(left, right, width, height):
    _, _, ids_a = unpack(left, width, height)
    _, _, ids_b = unpack(right, width, height)
    return {(index % width, index // width)
            for index in range(width * height) if ids_a[index] != ids_b[index]}


def depth_delta(left, right, width, height):
    _, depth_a, _ = unpack(left, width, height)
    _, depth_b, _ = unpack(right, width, height)
    pairs = [(a, b) for a, b in zip(depth_a, depth_b) if math.isfinite(a) and math.isfinite(b)]
    if not pairs:
        return {"finite_pairs": 0, "maximum": None, "mean": None,
                "pixels_over_1e-6": 0}
    deltas = [abs(a - b) for a, b in pairs]
    return {"finite_pairs": len(pairs), "maximum": max(deltas),
            "mean": sum(deltas) / len(deltas),
            "pixels_over_1e-6": sum(1 for delta in deltas if delta > 1e-6)}


def probe_row(channels, width, height, y, x_start, x_end):
    colors, depth, ids = unpack(channels, width, height)
    row = []
    for x in range(max(0, x_start), min(width - 1, x_end) + 1):
        index = y * width + x
        row.append({"x": x, "object": ids[index],
                    "depth": depth[index] if math.isfinite(depth[index]) else None,
                    "rgb": list(colors[index])})
    return row


def probe_box(channels, width, height, x_start, x_end, y_start, y_end):
    colors, depth, ids = unpack(channels, width, height)
    owners = {}
    for y in range(max(0, y_start), min(height - 1, y_end) + 1):
        for x in range(max(0, x_start), min(width - 1, x_end) + 1):
            index = y * width + x
            key = (ids[index], round(depth[index], 6) if math.isfinite(depth[index]) else "inf")
            owners[key] = owners.get(key, 0) + 1
    return sorted(({"object": key[0], "depth": key[1], "pixels": count}
                   for key, count in owners.items()),
                  key=lambda item: (-item["pixels"], str(item["depth"])))
