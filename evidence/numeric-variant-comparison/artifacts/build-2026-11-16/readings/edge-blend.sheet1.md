# EDGE-BLEND - THIN PART EDGE MIXING

Panels, left to right, top to bottom:

- 1 SERVICE COLOR (baseline)
- 2 RESEARCH COLOR (variant)
- 3 OWNERSHIP CHANGE SERVICE -> RESEARCH
- 4 COLOR DELTA SERVICE -> RESEARCH
- 5 SERVICE COLOR AT PROBE (x40)
- 6 RESEARCH COLOR AT PROBE

When a thin part covers only some supersamples, does the color blend mean ownership blended too?
RENDERER facet-raster-1   INPUT SHA256 80d3a7e7434958d3   SERVICE PLATE 2f8c775097b97083
RESEARCH VS SERVICE: color-only 205 px, ownership-changed 0 px (none), coverage -0 px
SERVICE ORACLE: agrees on 4964 px (0 ambiguous, 156 aggregate)   RESEARCH ORACLE: agrees on 4964 px (0 ambiguous, 156 aggregate)

READ FIRST: a color difference is not an ownership difference. Panels 3 and 4 are separate channels.
Panel 3 uses the object channel only: yellow = same coverage, different owner; blue = coverage lost;
green = coverage gained; dark = identical owner. Panel 4 uses the color channel only.
Transitions are (service object -> research object); full counts in readings/edge-blend.json.
Depth-bit changes: 0; see readings/edge-blend.json.
Service: renderer facet-raster-1, pinned in support/facetproof. Research: support/harness/variant.py.
Panels 5-6 are integer nearest-neighbour zooms of the probe window, not smoothed images.
