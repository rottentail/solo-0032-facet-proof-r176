import struct
import zlib
from .errors import require

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind, data):
    crc = zlib.crc32(kind + data) & 0xffffffff
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def encode_rgb(width, height, pixels):
    require(len(pixels) == width * height * 3, "image", "RGB byte count does not match extent", 500)
    rows = b"".join(b"\x00" + pixels[y*width*3:(y+1)*width*3] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b"")


def inspect_png(raw):
    require(raw[:8] == SIGNATURE, "png", "Invalid PNG signature", 422)
    cursor = 8
    types = []
    width = height = None
    while cursor + 12 <= len(raw):
        length = struct.unpack_from(">I", raw, cursor)[0]
        require(cursor + 12 + length <= len(raw), "png", "Truncated PNG", 422)
        kind = raw[cursor+4:cursor+8]
        data = raw[cursor+8:cursor+8+length]
        expected = struct.unpack_from(">I", raw, cursor+8+length)[0]
        require(zlib.crc32(kind+data) & 0xffffffff == expected, "png", "PNG CRC mismatch", 422)
        types.append(kind.decode("ascii"))
        if kind == b"IHDR":
            width, height = struct.unpack_from(">II", data)
        cursor += length + 12
        if kind == b"IEND":
            break
    require(types and types[0] == "IHDR" and types[-1] == "IEND" and cursor == len(raw),
            "png", "PNG chunk envelope invalid", 422)
    return {"width": width, "height": height, "chunks": types}
