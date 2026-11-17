from .algebra import add, scale, sub


def plane_distance(plane, vertex):
    return sum(plane[i] * vertex[i] for i in range(3)) + plane[3]


def clip_polygon(vertices, plane):
    if not vertices:
        return []
    output = []
    previous = vertices[-1]
    before = plane_distance(plane, previous)
    for current in vertices:
        after = plane_distance(plane, current)
        if (before >= 0) != (after >= 0):
            ratio = before / (before - after)
            output.append(add(previous, scale(sub(current, previous), ratio)))
        if after >= 0:
            output.append(current)
        previous, before = current, after
    return output


def clip_triangle(vertices, planes):
    polygon = vertices
    for plane in planes:
        polygon = clip_polygon(polygon, plane)
        if len(polygon) < 3:
            return []
    return [[polygon[0], polygon[i], polygon[i+1]] for i in range(1, len(polygon)-1)]
