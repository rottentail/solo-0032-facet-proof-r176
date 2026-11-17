"""Independent consumer using only Python's standard modules.

inspect_bundle(path) and validate_bundle(rawbytes) return JSON-safe dictionaries.
Invalid input returns {valid: False, error: stable_code, message: explanation}.
Passing establishes internal consistency, not external authenticity or a
currently valid review decision. No producer modules are imported.
"""
from .archive import load_file
from .errors import InvalidBundle
from .format import evaluate


def _rejection(exc):
    return {"valid": False, "error": exc.code, "message": exc.message}


def validate_bundle(rawbytes):
    try:
        return evaluate(rawbytes)[0]
    except InvalidBundle as exc:
        return _rejection(exc)


def inspect_bundle(path):
    try:
        return validate_bundle(load_file(path))
    except InvalidBundle as exc:
        return _rejection(exc)


__all__ = ["inspect_bundle", "validate_bundle"]
