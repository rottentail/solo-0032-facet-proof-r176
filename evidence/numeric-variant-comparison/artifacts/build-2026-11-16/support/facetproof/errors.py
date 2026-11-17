from contextlib import contextmanager
import sqlite3


class Fault(Exception):
    def __init__(self, code, detail, status=400):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status

    def as_dict(self):
        return {"error": self.code, "detail": self.detail}


def require(condition, code, detail, status=400):
    if not condition:
        raise Fault(code, detail, status)


@contextmanager
def storage_errors():
    try:
        yield
    except sqlite3.IntegrityError as exc:
        raise Fault("conflict", "Persistent identity or reference conflict", 409) from exc
    except sqlite3.OperationalError as exc:
        raise Fault("storage_busy", "Storage is unavailable; retry later", 503) from exc
