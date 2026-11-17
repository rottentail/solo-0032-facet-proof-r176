from .algebra import add, dot, scale, unit


def illuminate(normal, pigment, lighting, view_direction):
    if pigment["two_sided"] and dot(normal, view_direction) < 0:
        normal = scale(normal, -1)
    result = [v * lighting["ambient"] for v in pigment["linear"]]
    for emitter in lighting["lights"]:
        diffuse = max(0., dot(normal, emitter["direction"]))
        halfway = add(emitter["direction"], view_direction)
        specular = 0.
        if dot(halfway, halfway) > 1e-12 and diffuse > 0:
            exponent = 2 + (1 - pigment["roughness"]) ** 2 * 126
            specular = max(0., dot(normal, unit(halfway))) ** exponent * pigment["specular"]
        for channel in range(3):
            result[channel] += emitter["intensity"] * emitter["color"][channel] * (
                pigment["linear"][channel] * diffuse + specular)
    return [min(1., max(0., v)) for v in result]
