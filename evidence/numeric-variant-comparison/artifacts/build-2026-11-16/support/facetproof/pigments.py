from .values import identity, vector, scalar, text, object_value, boolean
from .errors import require


def srgb_to_linear(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def linear_to_srgb(value):
    value = min(1., max(0., value))
    return value * 12.92 if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055


def validate_pigment(data):
    object_value(data)
    rgb = vector(data.get("color"), "color", low=0, high=1)
    return {"name": text(data.get("name"), "name"), "color": rgb,
            "linear": [srgb_to_linear(v) for v in rgb],
            "roughness": scalar(data.get("roughness", .65), "roughness", .05, 1),
            "specular": scalar(data.get("specular", .2), "specular", 0, 1),
            "two_sided": boolean(data.get("two_sided", False), "two_sided")}


class Pigments:
    def __init__(self, db):
        self.db = db

    def create(self, data):
        payload = validate_pigment(data)
        with self.db.unit_of_work() as conn:
            return self.db.insert(conn, identity("pigment"), "pigment", "usable", payload)

    def revise(self, pigment_id, data):
        payload = validate_pigment(data)
        require("revision" in data, "revision", "Expected revision is required")
        with self.db.unit_of_work() as conn:
            obj = self.db.get(conn, pigment_id, "pigment")
            return self.db.update(conn, obj, payload, expected=data.get("revision"))
