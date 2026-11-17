import time
from .errors import Fault, require
from .planner import build_plan
from .tile_renderer import TileEngine
from .passes import serialize_passes
from .values import digest


class Worker:
    def __init__(self, db, exposures, plates, blobs):
        self.db, self.exposures, self.plates, self.blobs = db, exposures, plates, blobs
        self.tiles = TileEngine(db, exposures, blobs)

    def run_one(self):
        exposure = self.exposures.claim()
        if exposure is None:
            return {"state": "idle"}
        started = time.monotonic()
        last_check = [0.]

        def checkpoint():
            stamp = time.monotonic()
            require(stamp - started <= 45, "render_timeout", "Exposure exceeded 45 second render budget", 422)
            if stamp - last_check[0] >= .15:
                self.exposures.heartbeat(exposure["id"], exposure["token"])
                last_check[0] = stamp

        try:
            with self.db.unit_of_work() as conn:
                seal = self.db.get(conn, exposure["seal_id"], "seal")["payload"]
            plan = build_plan(seal, exposure["request"])
            checkpoint()
            rendered = self.tiles.render(exposure, plan, checkpoint)
            passes, statistics = serialize_passes(plan, rendered, exposure["request"])
            descriptors = {}
            for name, data in passes.items():
                checkpoint()
                descriptors[name] = self.blobs.put(data)
            payload = {"format": "facet-plate-1", "seal_id": exposure["seal_id"],
                       "seal_hash": seal["content_hash"], "request": exposure["request"],
                       "width": exposure["request"]["width"], "height": exposure["request"]["height"],
                       "lens_hash": plan["lens_hash"], "objects": plan["objects"],
                       "passes": descriptors, "statistics": statistics,
                       "visual_hash": digest(descriptors)}
            self.exposures.heartbeat(exposure["id"], exposure["token"])
            plate = self.plates.finish(exposure, payload)
            return {"state": "succeeded", "exposure_id": exposure["id"], "plate": plate}
        except Fault as exc:
            result = self.exposures.fail(exposure["id"], exposure["token"], exc.code)
            return {"state": result["state"], "exposure_id": exposure["id"], "error": exc.as_dict()}
        except (OSError, MemoryError) as exc:
            result = self.exposures.fail(exposure["id"], exposure["token"], "resource_failure")
            return {"state": result["state"], "exposure_id": exposure["id"], "error": "resource_failure"}
