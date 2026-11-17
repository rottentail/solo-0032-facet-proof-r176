"""Bounded ZIP input. No archive-controlled path is ever extracted."""
import io
from pathlib import Path
import stat
import struct
import zipfile
import zlib
from .errors import InvalidBundle, require

CHANNELS = frozenset({"color.rgb", "depth.f32", "object.u32",
                      "color.png", "depth.png", "object.png"})
MEMBERS = frozenset({"plate.json", "seal.json"}) | {
    "passes/" + name for name in CHANNELS}
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_BYTES = 128 * 1024 * 1024
MAX_SIDE = 512


def load_file(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidBundle("archive_read", "Cannot read the bundle file") from exc
    require(len(raw) <= MAX_ARCHIVE_BYTES, "archive_size", "Bundle exceeds input limit")
    return raw


def _limit(name):
    if name.endswith(".json"):
        return MAX_JSON_BYTES
    if name.endswith(".png"):
        return 4 * 1024 * 1024
    return MAX_SIDE * MAX_SIDE * (3 if name.endswith(".rgb") else 4)


def read_members(raw):
    require(isinstance(raw, (bytes, bytearray, memoryview)), "archive_type", "Expected ZIP bytes")
    require(len(raw) <= MAX_ARCHIVE_BYTES, "archive_size", "Bundle exceeds input limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = set()
            total = 0
            for entry in entries:
                name = entry.filename
                require(entry.orig_filename == name and "\\" not in name and ":" not in name
                        and not name.startswith("/")
                        and all(part not in {"", ".", ".."} for part in name.split("/")),
                        "archive_path", "Archive contains an unsafe member path")
                require(name not in names, "archive_duplicate", "Archive contains a duplicate member")
                names.add(name)
                require(not entry.is_dir() and stat.S_IFMT(entry.external_attr >> 16) in {0, stat.S_IFREG},
                        "archive_member_type", "Only regular archive members are allowed")
                require(not entry.flag_bits & 1, "archive_encrypted", "Encrypted members are unsupported")
                require(entry.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                        "archive_compression", "Unsupported ZIP compression")
                require(name in MEMBERS, "archive_members", "Unexpected archive member")
                require(0 <= entry.file_size <= _limit(name),
                        "archive_size", "Archive member exceeds decoded size limit")
                total += entry.file_size
                require(total <= MAX_UNPACKED_BYTES, "archive_size", "Decoded archive exceeds limit")
            require(names == MEMBERS, "archive_members", "Bundle must contain exactly two metadata files and six channels")
            result = {}
            for entry in entries:
                with archive.open(entry) as stream:
                    data = stream.read(_limit(entry.filename) + 1)
                require(len(data) == entry.file_size and len(data) <= _limit(entry.filename),
                        "archive_size", "Decoded member size disagrees with ZIP metadata")
                result[entry.filename] = data
            return result
    except InvalidBundle:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, OSError,
            EOFError, ValueError, UnicodeError, struct.error, NotImplementedError, zlib.error) as exc:
        raise InvalidBundle("archive_invalid", "Invalid ZIP structure, checksum, or compressed data") from exc
