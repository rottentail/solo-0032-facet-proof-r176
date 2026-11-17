import math
from .errors import require
from .values import vector


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def scale(a, k):
    return [x * k for x in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    length = norm(a)
    require(length > 1e-10, "direction", "Direction has zero length")
    return scale(a, 1 / length)


def identity_matrix():
    return [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def transform_matrix(data):
    translation = vector(data.get("translation", [0, 0, 0]), "translation", low=-10000, high=10000)
    angles = vector(data.get("euler", [0, 0, 0]), "euler", low=-3600, high=3600)
    sizes = vector(data.get("scale", [1, 1, 1]), "scale", low=-1000, high=1000)
    require(all(abs(x) >= 1e-5 for x in sizes), "singular", "Scale cannot collapse geometry")
    rx, ry, rz = [math.radians(x) for x in angles]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    euler = [[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
                [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx],
                [-sy, cy*sx, cy*cx]]
    matrix = identity_matrix()
    for row in range(3):
        for col in range(3):
            matrix[row][col] = euler[row][col] * sizes[col]
        matrix[row][3] = translation[row]
    return matrix


def point(matrix, value):
    return [sum(matrix[r][c] * value[c] for c in range(3)) + matrix[r][3]
            for r in range(3)]


def bounds(points):
    require(bool(points), "bounds", "Empty geometry has no bounds")
    return {"min": [min(p[a] for p in points) for a in range(3)],
            "max": [max(p[a] for p in points) for a in range(3)]}


def face_normal(vertices):
    return unit(cross(sub(vertices[1], vertices[0]), sub(vertices[2], vertices[0])))
