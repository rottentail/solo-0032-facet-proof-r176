"""Stable, transport-independent rejection codes for the offline reader."""


class InvalidBundle(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def require(condition, code, message):
    if not condition:
        raise InvalidBundle(code, message)
