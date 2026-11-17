"""Independent decoder for the bundle's opaque 8-bit RGB PNG contract."""
import struct
import zlib
from .archive import MAX_SIDE
from .errors import InvalidBundle, require

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(left, up, upper_left):
    prediction = left + up - upper_left
    distances = (abs(prediction-left), abs(prediction-up), abs(prediction-upper_left))
    return (left, up, upper_left)[distances.index(min(distances))]


def decode_rgb(raw, expected_width, expected_height):
    require(raw.startswith(SIGNATURE), "png_signature", "Invalid PNG signature")
    offset = len(SIGNATURE)
    seen_header = False
    seen_data = False
    ended_data = False
    finished = False
    compressed = bytearray()
    chunks = 0
    while offset < len(raw):
        require(offset + 12 <= len(raw), "png_chunks", "Truncated PNG chunk")
        length = struct.unpack_from(">I", raw, offset)[0]
        require(offset + length + 12 <= len(raw), "png_chunks", "PNG chunk exceeds input")
        kind = raw[offset+4:offset+8]
        data = raw[offset+8:offset+8+length]
        crc = struct.unpack_from(">I", raw, offset+8+length)[0]
        require(zlib.crc32(kind + data) & 0xffffffff == crc, "png_crc", "PNG chunk checksum mismatch")
        require(all(65 <= x <= 90 or 97 <= x <= 122 for x in kind)
                and not kind[2] & 32, "png_chunks", "Invalid PNG chunk type")
        chunks += 1
        require(chunks <= 4096, "png_chunks", "Too many PNG chunks")
        require(seen_header or kind == b"IHDR", "png_chunks", "IHDR must be first")
        if kind == b"IHDR":
            require(not seen_header and length == 13, "png_header", "Invalid or duplicate IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            require(1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE
                    and (width, height) == (expected_width, expected_height),
                    "png_extent", "PNG dimensions disagree with the plate")
            require((depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0),
                    "png_format", "Expected non-interlaced opaque 8-bit RGB PNG")
            seen_header = True
        elif kind == b"IDAT":
            require(not ended_data, "png_chunks", "IDAT chunks must be consecutive")
            seen_data = True
            compressed.extend(data)
        elif kind == b"IEND":
            require(seen_data and length == 0, "png_chunks", "Invalid IEND")
            finished = True
            offset += 12
            require(offset == len(raw), "png_chunks", "Unexpected bytes after IEND")
            break
        else:
            if seen_data:
                ended_data = True
            # Transparency would change the displayed image while leaving RGB
            # samples unchanged; it is outside this opaque channel contract.
            require(kind != b"tRNS" and (kind[0] & 32), "png_format", "Unsupported critical or transparency chunk")
        offset += length + 12
    require(finished, "png_chunks", "PNG is missing IEND")
    stride = expected_width * 3
    expected = expected_height * (stride + 1)
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(compressed, expected + 1)
    except zlib.error as exc:
        raise InvalidBundle("png_deflate", "Invalid PNG compressed stream") from exc
    require(len(decoded) == expected and inflater.eof and not inflater.unconsumed_tail
            and not inflater.unused_data, "png_deflate", "PNG decoded length or stream termination is invalid")
    pixels = bytearray(expected_height * stride)
    previous = bytearray(stride)
    for y in range(expected_height):
        start = y * (stride + 1)
        filtering = decoded[start]
        require(filtering <= 4, "png_filter", "Unsupported PNG row filter")
        row = bytearray(decoded[start+1:start+1+stride])
        for x in range(stride):
            left = row[x-3] if x >= 3 else 0
            up = previous[x]
            upper_left = previous[x-3] if x >= 3 else 0
            if filtering == 1:
                predictor = left
            elif filtering == 2:
                predictor = up
            elif filtering == 3:
                predictor = (left + up) // 2
            elif filtering == 4:
                predictor = _paeth(left, up, upper_left)
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        pixels[y*stride:(y+1)*stride] = row
        previous = row
    return bytes(pixels)
