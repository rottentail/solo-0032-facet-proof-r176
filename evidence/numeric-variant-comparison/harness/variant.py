"""Research numeric variant for Facet Proof plate rendering.

This module is intentionally independent of the service package: it imports
nothing from ``facetproof`` and never touches the database or blob store. It
consumes a frozen job (camera-space triangles, their already-computed linear
colors and object numbers, the frustum planes, and the canvas extent) and
produces raw final-plate channels. The harness builds that job through the
baseline pipeline itself, so geometry, culling, shading, and object numbering
are held constant.

The variant differs from the baseline in five documented, individually
switchable choices. Only the first three are expected to matter for the
scenarios in this bundle; the last two are numerical controls.

``edge_color``
    ``average`` averages linear color over all supersamples (baseline).
    ``nearest`` keeps the color of the nearest supersample, which is already
    the sample that supplies object id and depth. This changes edge pixels
    without changing any depth or ownership decision.

``tie_window``
    Absolute camera-forward-distance difference under which two fragments are
    considered equal. Both implementations give the tie to the lower object
    id, but the variant uses 4e-9 instead of 1e-9. Widening it changes which
    near-coplanar fragments count as equal.

``near_crossing``
    ``clip`` polygons against every frustum plane (baseline). ``reject`` drops
    any face with a camera-space vertex in front of the near plane instead of
    generating clipped geometry. It is a policy stand-in for "do not clip,
    remove the whole face" and is expected to lose coverage near the near
    plane. Faces that cross only side or far planes are still clipped normally.

``depth_interp``
    ``perspective`` interpolates camera-forward distance correctly as
    ``1 / sum(w_i / z_i)`` (baseline). ``screen_linear`` interpolates it
    linearly in screen space, ``sum(w_i * z_i)``. On strongly foreshortened or
    clipped triangles this is biased, and the bias can reorder surfaces whose
    true depths are close. This is a stand-in for the common mistake of
    treating post-projection depth as linear.

``edge_eval``
    ``direct`` evaluates all three edge functions at every sample (baseline).
    ``incremental`` walks them along x and down rows. Different rounding, same
    geometry policy; used to show that pure rounding is inert here.

``bary``
    ``divide`` divides edge values by triangle area (baseline). ``reciprocal``
    multiplies by a precomputed reciprocal and precomputes per-vertex
    reciprocal camera z for perspective depth. Also a rounding control.

With every switch at ``BASELINE`` the raw channels are byte-identical to the
service plate and the PNG previews are byte-identical too; the harness asserts
this on every scenario.

PNG previews are not encoded here. The harness encodes them with the service
PNG encoder and the baseline preview formulas, so PNG bytes remain attributable
to the pinned service implementation.
"""

from array import array
import math
import struct

RESEARCH_OPTIONS = {
    "edge_color": "nearest",
    "tie_window": 4e-9,
    "near_crossing": "clip",
    "depth_interp": "screen_linear",
    "edge_eval": "incremental",
    "bary": "reciprocal",
}



BASELINE_OPTIONS = {
    "edge_color": "average",
    "tie_window": 1e-9,
    "near_crossing": "clip",
    "depth_interp": "perspective",
    "edge_eval": "direct",
    "bary": "divide",
}

OPTION_KEYS = tuple(RESEARCH_OPTIONS)

# Diagnostic arms kept separate from the research default. ``reject`` is not a
# numeric reimplementation; it exists so the bundle can show that coverage loss
# is an ownership change, not a color approximation.
DIAGNOSTIC_ARMS = {
    "research": dict(RESEARCH_OPTIONS),
    "baseline": dict(BASELINE_OPTIONS),
    "reject-near-faces": dict(RESEARCH_OPTIONS, near_crossing="reject"),
    "average-edge-color": dict(RESEARCH_OPTIONS, edge_color="average"),
    "narrow-tie-window": dict(RESEARCH_OPTIONS, tie_window=1e-9),
    "perspective-depth": dict(RESEARCH_OPTIONS, depth_interp="perspective"),
    "direct-edges": dict(RESEARCH_OPTIONS, edge_eval="direct"),
    "divide-barycentrics": dict(RESEARCH_OPTIONS, bary="divide"),
}


def options(**overrides):
    merged = dict(RESEARCH_OPTIONS)
    for key, value in overrides.items():
        if key not in RESEARCH_OPTIONS:
            raise KeyError("unknown variant option: " + key)
        merged[key] = value
    return merged


def baseline_options():
    return dict(BASELINE_OPTIONS)


def _edge(a, b, x, y):
    return (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])


def _plane_distance(plane, vertex):
    return plane[0] * vertex[0] + plane[1] * vertex[1] + plane[2] * vertex[2] + plane[3]


def _clip_polygon(vertices, plane, reciprocal_ratio):
    if not vertices:
        return []
    output = []
    previous = vertices[-1]
    before = _plane_distance(plane, previous)
    for current in vertices:
        after = _plane_distance(plane, current)
        if (before >= 0) != (after >= 0):
            ratio = before * (1.0 / (before - after)) if reciprocal_ratio else before / (before - after)
            output.append([previous[0] + (current[0] - previous[0]) * ratio,
                           previous[1] + (current[1] - previous[1]) * ratio,
                           previous[2] + (current[2] - previous[2]) * ratio])
        if after >= 0:
            output.append(current)
        previous, before = current, after
    return output


def _clip_polygon_baseline(vertices, plane):
    """Literal transcription of the baseline clipper, for the clip ablation."""
    if not vertices:
        return []
    output = []
    previous = vertices[-1]
    before = _plane_distance(plane, previous)
    for current in vertices:
        after = _plane_distance(plane, current)
        if (before >= 0) != (after >= 0):
            ratio = before / (before - after)
            output.append([previous[0] + (current[0] - previous[0]) * ratio,
                           previous[1] + (current[1] - previous[1]) * ratio,
                           previous[2] + (current[2] - previous[2]) * ratio])
        if after >= 0:
            output.append(current)
        previous, before = current, after
    return output


def _clip_triangle(vertices, planes, reciprocal_ratio):
    polygon = vertices
    for plane in planes:
        polygon = (_clip_polygon(polygon, plane, reciprocal_ratio) if reciprocal_ratio
                   else _clip_polygon_baseline(polygon, plane))
        if len(polygon) < 3:
            return []
    return [[polygon[0], polygon[i], polygon[i + 1]] for i in range(1, len(polygon) - 1)]


def _project(job, vertex):
    x, y, z = vertex
    width, height = job["width"], job["height"]
    if job["projection"] == "perspective":
        half = math.tan(math.radians(job["fov"]) / 2)
        nx, ny = x / (z * half * width / height), y / (z * half)
    else:
        nx, ny = x / (job["span"] * width / height / 2), y / (job["span"] / 2)
    return [(nx + 1) * width / 2, (1 - ny) * height / 2, z]


def build_triangles(job, opts):
    near = job["near"]
    planes = job["planes"]
    reciprocal_ratio = opts["bary"] == "reciprocal"
    triangles = []
    for triangle in job["triangles"]:
        camera = triangle["camera_vertices"]
        if opts["near_crossing"] == "reject" and any(vertex[2] < near for vertex in camera):
            continue
        for clipped in _clip_triangle(camera, planes, reciprocal_ratio):
            triangles.append({
                "vertices": [_project(job, vertex) for vertex in clipped],
                "color": triangle["color"],
                "object_id": triangle["object_id"],
                "face": triangle["face"],
            })
    return {"width": job["width"], "height": job["height"],
            "projection": job["projection"], "background": job["background_linear"],
            "triangles": triangles, "options": dict(opts)}


def _keeps_current(distance, previous, object_id, previous_id, tie_window):
    """Baseline tie rule: farther loses; inside the window the higher id loses."""
    if distance > previous + tie_window:
        return True
    return abs(distance - previous) < tie_window and object_id >= previous_id


def rasterize(plan):
    opts = plan["options"]
    width, height = plan["width"], plan["height"]
    length = width * height
    depth = array("d", [math.inf]) * length
    ids = array("I", [0]) * length
    colors = array("f", [0.0]) * (length * 3)
    background = plan["background"]
    for pixel in range(length):
        colors[pixel * 3] = background[0]
        colors[pixel * 3 + 1] = background[1]
        colors[pixel * 3 + 2] = background[2]
    fragments = 0
    tie_window = opts["tie_window"]
    incremental = opts["edge_eval"] == "incremental"
    reciprocal = opts["bary"] == "reciprocal"
    for triangle in plan["triangles"]:
        a, b, c = triangle["vertices"]
        area = _edge(a, b, c[0], c[1])
        if abs(area) < 1e-10:
            continue
        inv_area = 1.0 / area if reciprocal else None
        left = max(0, math.floor(min(a[0], b[0], c[0])))
        right = min(width - 1, math.ceil(max(a[0], b[0], c[0])))
        top = max(0, math.floor(min(a[1], b[1], c[1])))
        bottom = min(height - 1, math.ceil(max(a[1], b[1], c[1])))
        if right < left or bottom < top:
            continue
        if reciprocal and plan["projection"] == "perspective":
            ia, ib, ic = 1.0 / a[2], 1.0 / b[2], 1.0 / c[2]
        else:
            ia = ib = ic = None
        # edge(p, q) = (q.x-p.x)(y-p.y) - (q.y-p.y)(x-p.x):
        # d/dx = p.y - q.y and d/dy = q.x - p.x.
        step_x_a, step_y_a = b[1] - c[1], c[0] - b[0]
        step_x_b, step_y_b = c[1] - a[1], a[0] - c[0]
        step_x_c, step_y_c = a[1] - b[1], b[0] - a[0]
        row_a = _edge(b, c, left + .5, top + .5) if incremental else None
        row_b = _edge(c, a, left + .5, top + .5) if incremental else None
        row_c = _edge(a, b, left + .5, top + .5) if incremental else None
        object_id = triangle["object_id"]
        color = triangle["color"]
        for y in range(top, bottom + 1):
            ea, eb, ec = row_a, row_b, row_c
            base = y * width
            for x in range(left, right + 1):
                if incremental:
                    edge_a, edge_b, edge_c = ea, eb, ec
                else:
                    edge_a = _edge(b, c, x + .5, y + .5)
                    edge_b = _edge(c, a, x + .5, y + .5)
                    edge_c = _edge(a, b, x + .5, y + .5)
                if reciprocal:
                    wa = edge_a * inv_area
                    wb = edge_b * inv_area
                    wc = 1 - wa - wb
                else:
                    wa = edge_a / area
                    wb = edge_b / area
                    wc = 1 - wa - wb
                if min(wa, wb, wc) < -1e-10:
                    if incremental:
                        ea += step_x_a
                        eb += step_x_b
                        ec += step_x_c
                    continue
                if plan["projection"] == "perspective" and opts["depth_interp"] == "perspective":
                    if reciprocal:
                        distance = 1.0 / (wa * ia + wb * ib + wc * ic)
                    else:
                        distance = 1 / (wa / a[2] + wb / b[2] + wc / c[2])
                else:
                    distance = wa * a[2] + wb * b[2] + wc * c[2]
                offset = base + x
                previous = depth[offset]
                if _keeps_current(distance, previous, object_id, ids[offset], tie_window):
                    if incremental:
                        ea += step_x_a
                        eb += step_x_b
                        ec += step_x_c
                    continue
                depth[offset] = distance
                ids[offset] = object_id
                colors[offset * 3] = color[0]
                colors[offset * 3 + 1] = color[1]
                colors[offset * 3 + 2] = color[2]
                fragments += 1
                if incremental:
                    ea += step_x_a
                    eb += step_x_b
                    ec += step_x_c
            if incremental:
                row_a += step_y_a
                row_b += step_y_b
                row_c += step_y_c
    return {"depth": depth, "ids": ids, "colors": colors,
            "fragments": fragments, "triangles": len(plan["triangles"])}


def _linear_to_srgb(value):
    value = min(1.0, max(0.0, value))
    return value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def downsample(plan, rendered, samples, color_policy):
    width, height = plan["width"] // samples, plan["height"] // samples
    colors = bytearray(width * height * 3)
    depth = bytearray(width * height * 4)
    ids = bytearray(width * height * 4)
    covered = 0
    for y in range(height):
        for x in range(width):
            offsets = [(y * samples + sy) * plan["width"] + x * samples + sx
                       for sy in range(samples) for sx in range(samples)]
            nearest = min(offsets, key=lambda p: (rendered["depth"][p], p))
            object_id = rendered["ids"][nearest]
            if object_id:
                covered += 1
            output = y * width + x
            if color_policy == "nearest":
                value = [rendered["colors"][nearest * 3 + channel] for channel in range(3)]
            elif color_policy == "average":
                value = [sum(rendered["colors"][p * 3 + channel] for p in offsets) / len(offsets)
                         for channel in range(3)]
            else:
                raise ValueError("unknown edge color policy")
            for channel in range(3):
                colors[output * 3 + channel] = round(_linear_to_srgb(value[channel]) * 255)
            struct.pack_into("<f", depth, output * 4, rendered["depth"][nearest])
            struct.pack_into("<I", ids, output * 4, object_id)
    return {"color.rgb": bytes(colors), "depth.f32": bytes(depth), "object.u32": bytes(ids),
            "covered_pixels": covered, "width": width, "height": height}


def render(job, opts=None, *, samples=None):
    """Render a frozen job to raw final-plate channels.

    Returns a dictionary with ``color.rgb``, ``depth.f32``, ``object.u32`` plus
    bookkeeping. It does not create plate metadata or PNGs.
    """
    opts = dict(RESEARCH_OPTIONS if opts is None else opts)
    samples = job["samples"] if samples is None else samples
    plan = build_triangles(job, opts)
    rendered = rasterize(plan)
    down = downsample(plan, rendered, samples, opts["edge_color"])
    return {"color.rgb": down["color.rgb"],
            "depth.f32": down["depth.f32"],
            "object.u32": down["object.u32"],
            "covered_pixels": down["covered_pixels"],
            "fragments": rendered["fragments"],
            "triangles": rendered["triangles"],
            "options": dict(opts)}
