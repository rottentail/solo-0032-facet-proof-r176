from .algebra import point, face_normal, unit, sub, dot
from .camera import frustum_planes, project, view_point
from .clipping import clip_triangle
from .errors import require
from .shading import illuminate
from .values import integer, digest
from .pigments import srgb_to_linear

RENDERER_REVISION = "facet-raster-1"


def validate_request(data):
    width = integer(data.get("width", 256), "width", 16, 512)
    height = integer(data.get("height", 256), "height", 16, 512)
    samples = integer(data.get("samples", 1), "samples", 1, 2)
    return {"width": width, "height": height, "samples": samples,
            "renderer": RENDERER_REVISION}


def build_plan(seal, request):
    width, height = request["width"] * request["samples"], request["height"] * request["samples"]
    lens = seal["lens"]
    planes = frustum_planes(lens, width, height)
    triangles = []
    objects = {}
    total_faces = sum(len(item["mesh"]["faces"]) for item in seal["closure"])
    require(total_faces <= 40000, "capacity", "Exposure exceeds 40000 source faces", 422)
    sorted_items = sorted(seal["closure"], key=lambda item: item["placement"]["key"])
    for object_id, item in enumerate(sorted_items, 1):
        placement, mesh, pigment = item["placement"], item["mesh"], item["pigment"]
        objects[str(object_id)] = {"key": placement["key"], "mesh_id": placement["mesh_id"],
                                   "pigment_id": placement["pigment_id"]}
        vertices = [point(placement["matrix"], v) for v in mesh["vertices"]]
        for face_number, face in enumerate(mesh["faces"]):
            world = [vertices[i] for i in face]
            normal = face_normal(world)
            center = [sum(v[a] for v in world) / 3 for a in range(3)]
            direction = sub(lens["eye"], center)
            if dot(direction, direction) < 1e-12:
                continue
            view_direction = unit(direction) if lens["projection"] == "perspective" else [-v for v in lens["forward"]]
            if not pigment["two_sided"] and dot(normal, view_direction) <= 0:
                continue
            color = illuminate(normal, pigment, seal["illumination"], view_direction)
            camera_vertices = [view_point(lens, v) for v in world]
            for clipped in clip_triangle(camera_vertices, planes):
                triangles.append({"vertices": [project(lens, v, width, height) for v in clipped],
                                  "color": color, "object_id": object_id, "face": face_number})
    return {"width": width, "height": height, "triangles": triangles, "objects": objects,
            "projection": lens["projection"], "background": [srgb_to_linear(c) for c in seal["illumination"]["background"]],
            "lens_hash": digest(lens), "source_faces": total_faces}
