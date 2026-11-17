import math
from .algebra import cross, dot, sub, unit
from .errors import require
from .values import choice, scalar, vector, integer


def validate_lens(data):
    eye = vector(data.get("eye", [4, 3, 5]), "eye", low=-10000, high=10000)
    target = vector(data.get("target", [0, 0, 0]), "target", low=-10000, high=10000)
    up = unit(vector(data.get("up", [0, 1, 0]), "up"))
    forward = unit(sub(target, eye))
    right = unit(cross(forward, up))
    true_up = unit(cross(right, forward))
    near = scalar(data.get("near", .1), "near", .001, 10000)
    far = scalar(data.get("far", 100), "far", .01, 100000)
    require(far > near, "lens", "Far plane must exceed near plane")
    return {"eye": eye, "target": target, "up": up, "right": right,
            "true_up": true_up, "forward": forward,
            "projection": choice(data.get("projection", "perspective"), "projection", {"perspective", "orthographic"}),
            "fov": scalar(data.get("fov", 45), "fov", 5, 150),
            "span": scalar(data.get("span", 5), "span", .01, 20000),
            "near": near, "far": far}


def view_point(lens, world):
    v = sub(world, lens["eye"])
    return [dot(v, lens["right"]), dot(v, lens["true_up"]), dot(v, lens["forward"])]


def project(lens, vertex, width, height):
    x, y, z = vertex
    if lens["projection"] == "perspective":
        half = math.tan(math.radians(lens["fov"]) / 2)
        nx, ny = x / (z * half * width / height), y / (z * half)
    else:
        nx, ny = x / (lens["span"] * width / height / 2), y / (lens["span"] / 2)
    return [(nx + 1) * width / 2, (1 - ny) * height / 2, z]


def frustum_planes(lens, width, height):
    planes = [(0, 0, 1, -lens["near"]), (0, 0, -1, lens["far"])]
    if lens["projection"] == "perspective":
        half_y = math.tan(math.radians(lens["fov"]) / 2)
        half_x = half_y * width / height
        planes += [(1, 0, half_x, 0), (-1, 0, half_x, 0),
                   (0, 1, half_y, 0), (0, -1, half_y, 0)]
    else:
        half_y = lens["span"] / 2
        half_x = half_y * width / height
        planes += [(1, 0, 0, half_x), (-1, 0, 0, half_x),
                   (0, 1, 0, half_y), (0, -1, 0, half_y)]
    return planes
