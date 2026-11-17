# PERSPECTIVE-CLIPPING - PERSPECTIVE CLIPPING

Panels, left to right, top to bottom:

- 1 SERVICE COLOR (baseline)
- 2 RESEARCH COLOR (variant)
- 3 OWNERSHIP CHANGE SERVICE -> RESEARCH
- 4 COLOR DELTA SERVICE -> RESEARCH
- 5 SERVICE COLOR AT PROBE (x24)
- 6 RESEARCH COLOR AT PROBE

When a triangle crosses the near plane, does clipped interpolation keep depth and ownership correct?
RENDERER facet-raster-1   INPUT SHA256 4848ae9802a67365   SERVICE PLATE 4e49e749aa3895ab
RESEARCH VS SERVICE: color-only 127 px, ownership-changed 21 px (1->3=21), coverage -0 px
SERVICE ORACLE: agrees on 6799 px (0 ambiguous, 113 aggregate)   RESEARCH ORACLE: DISAGREES: 17 ownership, 32 depth

READ FIRST: a color difference is not an ownership difference. Panels 3 and 4 are separate channels.
Panel 3 uses the object channel only: yellow = same coverage, different owner; blue = coverage lost;
green = coverage gained; dark = identical owner. Panel 4 uses the color channel only.
Transitions are (service object -> research object); full counts in readings/perspective-clipping.json.
Depth-bit changes: 3311; see readings/perspective-clipping.json.
Service: renderer facet-raster-1, pinned in support/facetproof. Research: support/harness/variant.py.
Panels 5-6 are integer nearest-neighbour zooms of the probe window, not smoothed images.
