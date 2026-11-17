"""Independent geometric oracle for plate ownership and depth.

The oracle shares no rasterization code with either implementation. It casts a
ray through every supersample centre in camera space and intersects it with the
frozen, already-culled triangles using Moller-Trumbore. A hit's ray parameter
with a unit-z direction is exactly the camera-forward distance the plate's
depth channel reports, so depth and ownership are checked together.

Two distinctions matter for reading the sheets:

* *Ambiguous* pixels are those where two different objects are hit at nearly
  equal distance (within ``AMBIGUOUS_WINDOW``). Geometry alone does not decide
  them; the renderer's tie policy does. The oracle reports them and does not
  count them as disagreements.
* *Aggregate* pixels are those where the supersamples of one plate pixel
  disagree about the visible object. This is legitimate: the plate takes object
  id and depth from the nearest supersample while color may average. The oracle
  reports the per-supersample verdicts but does not predict the aggregate.

Everything else must match: if all supersamples see one unambiguous object, the
plate must report that object at that pixel and a depth equal to the nearest
supersample's hit distance.
"""
import math

AMBIGUOUS_WINDOW = 1e-7
DEPTH_RELATIVE_TOLERANCE = 1e-6


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _intersect(origin, direction, triangle):
    """Moller-Trumbore; returns the ray parameter or None.

    ``direction`` has unit z, so the parameter equals camera-forward distance.
    Both face orientations are accepted because culling already happened in the
    frozen job.
    """
    v0, v1, v2 = triangle
    e1 = _sub(v1, v0)
    e2 = _sub(v2, v0)
    pvec = _cross(direction, e2)
    det = _dot(e1, pvec)
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    tvec = _sub(origin, v0)
    u = _dot(tvec, pvec) * inv
    if u < -1e-12 or u > 1 + 1e-12:
        return None
    qvec = _cross(tvec, e1)
    v = _dot(direction, qvec) * inv
    if v < -1e-12 or u + v > 1 + 1e-12:
        return None
    return _dot(e2, qvec) * inv


def _hits(job, nx, ny):
    """All intersections for a normalised canvas coordinate, sorted near to far."""
    half = math.tan(math.radians(job["fov"]) / 2)
    aspect = job["width"] / job["height"]
    direction = (nx * half * aspect, ny * half, 1.0)
    hits = []
    for triangle in job["triangles"]:
        t = _intersect((0.0, 0.0, 0.0), direction, triangle["camera_vertices"])
        if t is None:
            continue
        if job["near"] <= t <= job["far"]:
            hits.append((t, triangle["object_id"]))
    hits.sort()
    return hits


def supersample_verdict(job, sx, sy):
    """Verdict for one supersample centre in canvas pixel coordinates."""
    width, height = job["width"], job["height"]
    nx = 2.0 * (sx + 0.5) / width - 1.0
    ny = 1.0 - 2.0 * (sy + 0.5) / height
    hits = _hits(job, nx, ny)
    if not hits:
        return {"object": 0, "distance": None, "ambiguous": False, "candidates": []}
    nearest_distance, nearest_object = hits[0]
    candidates = [(distance, object_id) for distance, object_id in hits
                  if object_id != nearest_object
                  and abs(distance - nearest_distance) <= AMBIGUOUS_WINDOW]
    return {"object": nearest_object, "distance": nearest_distance,
            "ambiguous": bool(candidates), "candidates": candidates}


def check(job, channels, width, height, samples):
    """Compare every plate pixel against supersampled ray verdicts."""
    import struct
    ids = struct.unpack("<%dI" % (width * height), channels["object.u32"])
    depth = struct.unpack("<%df" % (width * height), channels["depth.f32"])
    report = {
        "method": "camera-space ray cast, Moller-Trumbore, no edge functions",
        "ambiguous_window": AMBIGUOUS_WINDOW,
        "depth_relative_tolerance": DEPTH_RELATIVE_TOLERANCE,
        "checked_pixels": 0,
        "ambiguous_pixels": 0,
        "aggregate_disagreements": 0,
        "ownership_mismatches": [],
        "depth_mismatches": [],
    }
    for y in range(height):
        for x in range(width):
            verdicts = [supersample_verdict(job, x * samples + sx, y * samples + sy)
                        for sy in range(samples) for sx in range(samples)]
            owners = {verdict["object"] for verdict in verdicts}
            if any(verdict["ambiguous"] for verdict in verdicts):
                report["ambiguous_pixels"] += 1
                continue
            if len(owners) != 1:
                report["aggregate_disagreements"] += 1
                continue
            expected_object = next(iter(owners))
            expected_distance = min(verdict["distance"] for verdict in verdicts
                                    if verdict["distance"] is not None) if expected_object else None
            report["checked_pixels"] += 1
            index = y * width + x
            if ids[index] != expected_object:
                if len(report["ownership_mismatches"]) < 32:
                    report["ownership_mismatches"].append(
                        {"x": x, "y": y, "plate_object": ids[index],
                         "oracle_object": expected_object,
                         "oracle_distance": expected_distance})
                continue
            if expected_object == 0:
                continue
            observed = depth[index]
            if not math.isfinite(observed) or \
                    abs(observed - expected_distance) > DEPTH_RELATIVE_TOLERANCE * max(1.0, expected_distance):
                if len(report["depth_mismatches"]) < 32:
                    report["depth_mismatches"].append(
                        {"x": x, "y": y, "plate_depth": observed if math.isfinite(observed) else None,
                         "oracle_distance": expected_distance})
    report["ownership_mismatch_count"] = len(report["ownership_mismatches"])
    report["depth_mismatch_count"] = len(report["depth_mismatches"])
    report["agrees"] = not report["ownership_mismatches"] and not report["depth_mismatches"]
    return report
