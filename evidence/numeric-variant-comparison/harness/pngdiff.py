"""Small deterministic PNG utilities for comparison sheets and zooms.

Encoding uses the service PNG encoder from the pinned implementation, so these
images share exactly one encoder with the plates. Composition and scaling are
nearest-neighbour and pure integer arithmetic; no resampling is hidden here.
"""
import io
import struct

from facetproof.png import encode_rgb


def compose(panels, gap=6, background=(255, 255, 255)):
    """Place panels left to right on a common background.

    ``panels`` is a list of ``(width, height, rgb_bytes)``. All panels must have
    the same height. Panels are separated by a ``gap``-pixel background column
    so that no edge of one image touches another.
    """
    if not panels:
        raise ValueError("no panels")
    height = panels[0][1]
    if any(panel[1] != height for panel in panels):
        raise ValueError("panel heights differ")
    width = sum(panel[0] for panel in panels) + gap * (len(panels) - 1)
    out = bytearray(background * (width * height))
    cursor = 0
    for panel_width, panel_height, rgb in panels:
        for y in range(panel_height):
            target = (y * width + cursor) * 3
            out[target:target + panel_width * 3] = rgb[y * panel_width * 3:(y + 1) * panel_width * 3]
        cursor += panel_width + gap
    return width, height, bytes(out)


def crop(width, rgb, x0, y0, x1, y1):
    height = len(rgb) // (width * 3)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    out = bytearray()
    for y in range(y0, y1):
        out += rgb[(y * width + x0) * 3:(y * width + x1) * 3]
    return x1 - x0, y1 - y0, bytes(out)


def scale(width, height, rgb, factor):
    out = bytearray()
    for y in range(height):
        row = rgb[y * width * 3:(y + 1) * width * 3]
        expanded = bytearray()
        for x in range(width):
            pixel = row[x * 3:x * 3 + 3]
            expanded += pixel * factor
        out += bytes(expanded) * factor
    return width * factor, height * factor, bytes(out)


def color_delta_rgb(width, height, left_rgb, right_rgb):
    """Grayscale of the maximum absolute per-channel difference."""
    out = bytearray(width * height * 3)
    for pixel in range(width * height):
        delta = max(abs(left_rgb[pixel * 3 + channel] - right_rgb[pixel * 3 + channel])
                    for channel in range(3))
        for channel in range(3):
            out[pixel * 3 + channel] = delta
    return bytes(out)


def ownership_map_rgb(width, height, left_ids, right_ids):
    """Gray = same owner, yellow = owner changed, blue = lost, green = gained."""
    out = bytearray(width * height * 3)
    for pixel in range(width * height):
        left = struct.unpack_from("<I", left_ids, pixel * 4)[0]
        right = struct.unpack_from("<I", right_ids, pixel * 4)[0]
        if left == right:
            color = (38, 40, 44)
        elif left and not right:
            color = (64, 124, 255)
        elif right and not left:
            color = (0, 190, 110)
        else:
            color = (252, 208, 0)
        out[pixel * 3:pixel * 3 + 3] = bytes(color)
    return bytes(out)


def color_delta_png(width, height, left_rgb, right_rgb):
    return encode_rgb(width, height, color_delta_rgb(width, height, left_rgb, right_rgb))


def ownership_map_png(width, height, left_ids, right_ids):
    return encode_rgb(width, height, ownership_map_rgb(width, height, left_ids, right_ids))


def coverage_map_png(width, height, ids, foreground=(245, 245, 245), background=(20, 20, 20)):
    """Binary silhouette from the identifier channel."""
    out = bytearray(width * height * 3)
    for pixel in range(width * height):
        owner = struct.unpack_from("<I", ids, pixel * 4)[0]
        out[pixel * 3:pixel * 3 + 3] = bytes(foreground if owner else background)
    return encode_rgb(width, height, bytes(out))


def encode_rgb_bytes(width, height, rgb):
    return encode_rgb(width, height, rgb)


def write(path, png_bytes):
    path.write_bytes(png_bytes)
