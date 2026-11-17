import hashlib
import json
import math
import re
import time
import uuid
from .errors import Fault, require


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identity(prefix):
    return prefix + "_" + uuid.uuid4().hex


def now():
    return time.time()


def object_value(value, field="body"):
    require(isinstance(value, dict), "shape", f"{field} must be an object")
    return value


def text(value, field, maximum=120):
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum,
            "text", f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def scalar(value, field, low=-1e6, high=1e6):
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            "number", f"{field} must be numeric")
    require(low <= value <= high and math.isfinite(value),
            "range", f"{field} outside [{low}, {high}]")
    return float(value)


def integer(value, field, low, high):
    require(isinstance(value, int) and not isinstance(value, bool) and low <= value <= high,
            "integer", f"{field} must be an integer within [{low}, {high}]")
    return value


def vector(value, field, length=3, low=-1e6, high=1e6):
    require(isinstance(value, (list, tuple)) and len(value) == length,
            "vector", f"{field} needs {length} components")
    return [scalar(x, field, low, high) for x in value]


def boolean(value, field):
    require(isinstance(value, bool), "boolean", f"{field} must be boolean")
    return value


def choice(value, field, allowed):
    require(isinstance(value, str) and value in allowed, "choice", f"{field} must be one of {sorted(allowed)}")
    return value


def key(value, field="key"):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", value),
            "key", f"{field} contains unsupported characters")
    return value


def parse_json(raw):
    try:
        return json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise Fault("json", "Expected finite JSON data") from exc
