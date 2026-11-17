# COPLANAR-OWNERSHIP - COPLANAR OWNERSHIP

Panels, left to right, top to bottom:

- 1 SERVICE COLOR (baseline)
- 2 RESEARCH COLOR (variant)
- 3 OWNERSHIP CHANGE SERVICE -> RESEARCH
- 4 COLOR DELTA SERVICE -> RESEARCH
- 5 SERVICE COLOR AT PROBE (x40)
- 6 RESEARCH COLOR AT PROBE

When two parts meet at the same depth, is the difference color or ownership? Does the variant move ownership?
RENDERER facet-raster-1   INPUT SHA256 929222e1d0d85d43   SERVICE PLATE b8f0d5c847e0fcaa
RESEARCH VS SERVICE: color-only 178 px, ownership-changed 252 px (2->1=252), coverage -0 px
SERVICE ORACLE: agrees on 5988 px (256 ambiguous, 156 aggregate)   RESEARCH ORACLE: agrees on 5988 px (256 ambiguous, 156 aggregate)

READ FIRST: a color difference is not an ownership difference. Panels 3 and 4 are separate channels.
Panel 3 uses the object channel only: yellow = same coverage, different owner; blue = coverage lost;
green = coverage gained; dark = identical owner. Panel 4 uses the color channel only.
Transitions are (service object -> research object); full counts in readings/coplanar-ownership.json.
Depth-bit changes: 0; see readings/coplanar-ownership.json.
Service: renderer facet-raster-1, pinned in support/facetproof. Research: support/harness/variant.py.
Panels 5-6 are integer nearest-neighbour zooms of the probe window, not smoothed images.
