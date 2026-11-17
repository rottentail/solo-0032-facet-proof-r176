"""Self-describing comparison sheets.

Each sheet is a PNG with labels baked in so it can be read after it leaves this
directory. Layout, top to bottom:

    title
    header lines: scenario question, provenance, reading for each row
    grid of panels, each with a label above it
    legend lines

Image scaling is nearest-neighbour. All text uses the local bitmap font. Panels
are scaled by an integer factor so the sheet is sharp on any viewer.
"""
import font
import pngdiff

INK = (17, 17, 17)
MUTED = (84, 88, 94)
BACKGROUND = (250, 251, 252)
RULE = (205, 211, 218)
PANEL_BACKGROUND = (235, 238, 242)

MARGIN = 16
GAP = 14
LINE = 11
TITLE_LINE = 18
LABEL_BLOCK = 20


def _fit(panel, box_width, box_height):
    panel_width, panel_height, rgb = panel
    factor = max(1, min(box_width // panel_width, box_height // panel_height))
    if factor > 1:
        panel_width, panel_height, rgb = pngdiff.scale(panel_width, panel_height, rgb, factor)
    width = min(box_width, panel_width)
    height = min(box_height, panel_height)
    if (width, height) != (panel_width, panel_height):
        width, height, rgb = pngdiff.crop(panel_width, rgb, 0, 0, width, height)
    return width, height, rgb, factor


def _blit(canvas, sheet_width, sheet_height, x, y, width, height, rgb):
    for row in range(height):
        target = ((y + row) * sheet_width + x) * 3
        canvas[target:target + width * 3] = rgb[row * width * 3:(row + 1) * width * 3]


def _frame(canvas, sheet_width, x, y, width, height, color):
    for offset in range(width):
        for edge in (y, y + height - 1):
            position = (edge * sheet_width + x + offset) * 3
            canvas[position:position + 3] = bytes(color)
    for offset in range(height):
        for edge in (x, x + width - 1):
            position = ((y + offset) * sheet_width + edge) * 3
            canvas[position:position + 3] = bytes(color)


def render(title, header_lines, panels, legend_lines, cell_width=360,
           cell_height=290, columns=3, sheet_width=1180):
    rows = (len(panels) + columns - 1) // columns
    header_height = MARGIN + TITLE_LINE + len(header_lines) * LINE + 12
    row_height = LABEL_BLOCK + cell_height + GAP
    legend_height = len(legend_lines) * LINE + MARGIN
    sheet_height = header_height + rows * row_height + legend_height
    canvas = bytearray(bytes(BACKGROUND) * (sheet_width * sheet_height))

    font.draw_text(canvas, sheet_width, sheet_height, MARGIN, MARGIN, title[:140], scale=2)
    y = MARGIN + TITLE_LINE
    for line in header_lines:
        font.draw_text(canvas, sheet_width, sheet_height, MARGIN, y, line[:250], scale=1, color=MUTED)
        y += LINE

    for index, panel in enumerate(panels):
        column = index % columns
        row = index // columns
        x = MARGIN + column * (cell_width + GAP)
        top = header_height + row * row_height
        font.draw_text(canvas, sheet_width, sheet_height, x, top, panel["label"][:64], scale=1)
        if panel.get("sublabel"):
            font.draw_text(canvas, sheet_width, sheet_height, x, top + LINE,
                           panel["sublabel"][:64], scale=1, color=MUTED)
        box_y = top + LABEL_BLOCK
        _frame(canvas, sheet_width, x, box_y, cell_width, cell_height, PANEL_BACKGROUND)
        width, height, rgb, _ = _fit(panel["image"], cell_width - 4, cell_height - 4)
        _blit(canvas, sheet_width, sheet_height, x + 2, box_y + 2, width, height, rgb)
        if panel.get("note"):
            font.draw_text(canvas, sheet_width, sheet_height, x + 4, box_y + cell_height - 12,
                           panel["note"][:60], scale=1, color=(255, 255, 255))

    y = header_height + rows * row_height
    for line in legend_lines:
        font.draw_text(canvas, sheet_width, sheet_height, MARGIN, y, line[:250], scale=1, color=MUTED)
        y += LINE
    return pngdiff.encode_rgb_bytes(sheet_width, sheet_height, bytes(canvas))
