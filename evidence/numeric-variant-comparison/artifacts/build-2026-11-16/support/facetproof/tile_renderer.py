"""Resume high-sample raster windows, then assemble for existing passes."""
from .raster import rasterize
from .tile_protocol import assemble, encode
from .tile_store import TileStore


class TileEngine:
    def __init__(self, db, exposures, blobs, *, tile_size=64):
        self.store = TileStore(db, exposures, blobs)
        self.blobs, self.tile_size = blobs, tile_size

    def render(self, exposure, plan, checkpoint):
        frame, records = self.store.prepare(exposure, plan, self.tile_size)
        for record in records:
            checkpoint()
            if record["state"] == "complete":
                continue
            # Window bounds stay in the original global sample coordinates.
            # Re-triangulation or shifting float vertices would change edge
            # evaluation and could change f64 depth or coplanar ownership.
            rendered = rasterize(plan, checkpoint, tuple(record["bounds"]))
            payload = encode(rendered, record["bounds"], frame["fingerprint"], self.blobs)
            checkpoint()
            self.store.commit(exposure, record["ordinal"], payload)
        self.store.assert_owned(exposure)
        frame, records = self.store.snapshot(exposure["id"])
        result = assemble(plan, records, frame["tile_size"], frame["fingerprint"], self.blobs, checkpoint)
        self.store.assert_owned(exposure)
        return result

    def progress(self, exposure_id):
        return self.store.progress(exposure_id)
