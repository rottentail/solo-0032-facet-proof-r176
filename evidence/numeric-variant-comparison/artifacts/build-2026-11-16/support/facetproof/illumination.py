from .algebra import unit
from .values import vector, scalar
from .errors import require


def validate_illumination(data):
    lights = data.get("lights", [{"direction": [1, 2, 3], "intensity": .8, "color": [1, 1, 1]}])
    require(isinstance(lights, list) and 1 <= len(lights) <= 8,
            "lights", "Expected 1..8 directional emitters")
    clean = []
    for light in lights:
        require(isinstance(light, dict), "light", "Emitter must be an object")
        clean.append({"direction": unit(vector(light.get("direction"), "direction")),
                      "intensity": scalar(light.get("intensity", 1), "intensity", 0, 4),
                      "color": vector(light.get("color", [1, 1, 1]), "light.color", low=0, high=1)})
    return {"lights": clean, "ambient": scalar(data.get("ambient", .16), "ambient", 0, 1),
            "background": vector(data.get("background", [.93, .95, .97]), "background", low=0, high=1)}
