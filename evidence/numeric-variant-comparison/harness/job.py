"""Frozen render jobs and baseline renders from frozen inputs.

The materials pin exactly what the numeric stages consume. ``normalize_input``
copies the render-relevant part of a frozen seal without database identifiers;
``frozen_job_from_input`` reproduces the baseline pre-clip work (placement,
winding, culling, shading, object numbering) from that copy; and
``baseline_from_input`` runs the baseline clipping/raster/pass code on it with
no database. ``render_input_digest`` covers only values that can change output.
"""
import math
import struct

from facetproof.algebra import dot, face_normal, point, sub, unit
from facetproof.camera import frustum_planes, view_point
from facetproof.passes import serialize_passes
from facetproof.pigments import srgb_to_linear
from facetproof.planner import build_plan
from facetproof.raster import rasterize
from facetproof.shading import illuminate
from facetproof.values import canonical, digest

RENDERER_REVISION = "facet-raster-1"

PIGMENT_FIELDS = ("linear", "two_sided", "roughness", "specular")


def normalize_input(seal, request):
    """Copy the render-relevant frozen inputs; no assembly, plate or blob ids."""
    lens = seal["lens"]
    closure = []
    for item in sorted(seal["closure"], key=lambda value: value["placement"]["key"]):
        placement = item["placement"]
        mesh = item["mesh"]
        pigment = item["pigment"]
        closure.append({
            "key": placement["key"],
            "matrix": placement["matrix"],
            "mesh": {"vertices": mesh["vertices"], "faces": mesh["faces"]},
            "pigment": {field: pigment[field] for field in PIGMENT_FIELDS},
            "mesh_revision": item["mesh_revision"],
            "pigment_revision": item["pigment_revision"],
        })
    return {
        "format": "facet-numeric-comparison-input-1",
        "lens": {key: lens[key] for key in
                 ("eye", "target", "up", "right", "true_up", "forward",
                  "projection", "fov", "span", "near", "far")},
        "illumination": seal["illumination"],
        "closure": closure,
        "request": dict(request),
    }


def render_input_digest(frozen):
    """Digest of only the values that determine the rendered channels."""
    material = {
        "lens": frozen["lens"],
        "illumination": frozen["illumination"],
        "closure": [{"key": item["key"], "matrix": item["matrix"],
                     "mesh": item["mesh"],
                     "pigment": item["pigment"]}
                    for item in frozen["closure"]],
        "request": {key: frozen["request"][key]
                    for key in ("width", "height", "samples", "renderer")},
    }
    return digest(material)


def _pseudo_seal(frozen):
    """A seal-shaped dictionary that ``build_plan`` accepts."""
    closure = []
    for item in frozen["closure"]:
        closure.append({
            "placement": {"key": item["key"], "matrix": item["matrix"],
                          "mesh_id": "frozen:" + item["key"],
                          "pigment_id": "frozen:" + item["key"],
                          "visible": True},
            "mesh": item["mesh"],
            "pigment": item["pigment"],
            "mesh_revision": item["mesh_revision"],
            "pigment_revision": item["pigment_revision"],
        })
    return {"lens": frozen["lens"], "illumination": frozen["illumination"],
            "closure": closure}


def frozen_job_from_input(frozen):
    """Pre-clip workspace: camera triangles, colors, object ids, planes, extent."""
    lens = frozen["lens"]
    request = frozen["request"]
    width = request["width"] * request["samples"]
    height = request["height"] * request["samples"]
    planes = frustum_planes(lens, width, height)
    triangles = []
    objects = {}
    for object_id, item in enumerate(frozen["closure"], 1):
        mesh, pigment = item["mesh"], item["pigment"]
        objects[str(object_id)] = {"key": item["key"],
                                   "mesh_id": "frozen:" + item["key"],
                                   "pigment_id": "frozen:" + item["key"]}
        vertices = [point(item["matrix"], v) for v in mesh["vertices"]]
        for face_number, face in enumerate(mesh["faces"]):
            world = [vertices[index] for index in face]
            normal = face_normal(world)
            center = [sum(vertex[axis] for vertex in world) / 3 for axis in range(3)]
            direction = sub(lens["eye"], center)
            if dot(direction, direction) < 1e-12:
                continue
            view_direction = unit(direction) if lens["projection"] == "perspective" else [-v for v in lens["forward"]]
            if not pigment["two_sided"] and dot(normal, view_direction) <= 0:
                continue
            color = illuminate(normal, pigment, frozen["illumination"], view_direction)
            triangles.append({"camera_vertices": [view_point(lens, vertex) for vertex in world],
                              "color": color, "object_id": object_id, "face": face_number})
    return {
        "width": width, "height": height, "samples": request["samples"],
        "projection": lens["projection"], "fov": lens["fov"],
        "span": lens["span"], "near": lens["near"], "far": lens["far"],
        "planes": planes,
        "background_linear": [srgb_to_linear(c) for c in frozen["illumination"]["background"]],
        "triangles": triangles, "objects": objects,
        "request": dict(request),
    }


def baseline_from_input(frozen):
    """Re-render the frozen inputs with the baseline pipeline, no database."""
    seal = _pseudo_seal(frozen)
    request = frozen["request"]
    plan = build_plan(seal, request)
    rendered = rasterize(plan, lambda: None)
    passes, statistics = serialize_passes(plan, rendered, request)
    return {"passes": passes, "statistics": statistics,
            "plan_triangles": len(plan["triangles"]),
            "plan_objects": plan["objects"],
            "plan_width": plan["width"], "plan_height": plan["height"]}


def previews(width, height, channels):
    """Encode PNG previews from raw channels using the service preview formulas."""
    from facetproof.png import encode_rgb
    depth = channels["depth.f32"]
    ids = channels["object.u32"]
    depth_rgb = bytearray(width * height * 3)
    object_rgb = bytearray(width * height * 3)
    for pixel in range(width * height):
        object_id = struct.unpack_from("<I", ids, pixel * 4)[0]
        distance = struct.unpack_from("<f", depth, pixel * 4)[0]
        shade = round(255 / (1 + distance)) if math.isfinite(distance) else 0
        for channel in range(3):
            depth_rgb[pixel * 3 + channel] = shade
            object_rgb[pixel * 3 + channel] = ((object_id * (73, 151, 199)[channel]) % 255) if object_id else 0
    return {"color.png": encode_rgb(width, height, channels["color.rgb"]),
            "depth.png": encode_rgb(width, height, bytes(depth_rgb)),
            "object.png": encode_rgb(width, height, bytes(object_rgb))}


def canonical_input(frozen):
    return canonical(frozen)
