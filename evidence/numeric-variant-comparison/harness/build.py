"""Build a pinned comparison bundle.

Run from the repository root:

    python3 -I evidence/numeric-variant-comparison/harness/build.py \
        --output evidence/numeric-variant-comparison/artifacts/<build-id>

The output directory is new and is never overwritten. Its name is chosen by the
caller; the build digest is written into ``manifest.json`` and printed. Later
edits to these scripts do not change what the directory means, because the
directory contains a copy of the exact scripts and renderer modules used
(``support/``), the frozen input each plate was rendered from, the plate bytes
with their SHA-256, and a digest over the whole record.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import compare  # noqa: E402
import font  # noqa: E402
import job  # noqa: E402
import keyorder  # noqa: E402
import oracle  # noqa: E402
import pngdiff  # noqa: E402
import scenario  # noqa: E402
import sheet  # noqa: E402
import variant  # noqa: E402
from facetproof.application import Application  # noqa: E402
from facetproof.routing import PREFIX, route_request  # noqa: E402
from facetreader import validate_bundle  # noqa: E402
from facetreader.png import decode_rgb  # noqa: E402

SCENARIOS = ("edge-blend", "coplanar-ownership", "perspective-clipping")
SERVICE_MODULES = ("planner.py", "raster.py", "passes.py", "clipping.py", "camera.py",
                   "shading.py", "png.py", "worker.py", "tile_renderer.py",
                   "tile_protocol.py", "pigments.py", "algebra.py", "values.py",
                   "errors.py", "illumination.py")
HARNESS_MODULES = ("variant.py", "job.py", "compare.py", "oracle.py", "pngdiff.py",
                   "sheet.py", "font.py", "scenario.py", "keyorder.py")
TOOL_MODULES = ("build.py", "verify.py", "drift.py")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_spec(name):
    return json.loads((ROOT / "evidence" / "numeric-variant-comparison"
                       / "scenarios" / (name + ".json")).read_text(encoding="utf-8"))


def probe_center(spec):
    probe = spec["probe"]
    if probe["kind"] == "row":
        return (probe["x_start"] + probe["x_end"]) // 2, probe["y"]
    return ((probe["x_start"] + probe["x_end"]) // 2,
            (probe["y_start"] + probe["y_end"]) // 2)


class Writer:
    def __init__(self, destination):
        self.destination = destination
        self.files = {}

    def write(self, relative, raw):
        target = self.destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        self.files[str(relative)] = {"sha256": sha(raw), "size": len(raw)}
        return raw


def arm_channels(frozen, arm, width, height):
    rendered = variant.render(job.frozen_job_from_input(frozen), variant.DIAGNOSTIC_ARMS[arm])
    previews = job.previews(width, height, rendered)
    return {"color.rgb": rendered["color.rgb"], "depth.f32": rendered["depth.f32"],
            "object.u32": rendered["object.u32"], **previews}, rendered


def zoom(panel, center, half, factor):
    width, rgb = panel
    x, y = center
    cropped = pngdiff.crop(width, rgb, x - half, y - half, x + half, y + half)
    return pngdiff.scale(*cropped, factor)


def arm_label(arm):
    return {
        "service": "SERVICE COLOR (baseline)",
        "research": "RESEARCH COLOR (variant)",
        "reject-near-faces": "REJECT NEAR FACES (coverage)",
        "average-edge-color": "AVERAGE EDGE COLOR (reverts nearest-color)",
        "narrow-tie-window": "NARROW TIE WINDOW (reverts 4e-9)",
        "perspective-depth": "PERSPECTIVE DEPTH (reverts screen-linear)",
        "direct-edges": "DIRECT EDGE EVALUATION (reverts incremental)",
        "divide-barycentrics": "DIVIDED BARYCENTRICS (reverts reciprocal)",
    }[arm]


def short(hash_value, length=12):
    return hash_value[:length]


def http(app):
    def call(method, route, data=None):
        return route_request(app, method, PREFIX + route, data)

    return call


def companion_key_order(writer):
    """Two plates that differ only in placement keys, plus service comparison."""
    spec = json.loads((ROOT / "evidence" / "numeric-variant-comparison" / "scenarios"
                       / "key-order.json").read_text(encoding="utf-8"))
    width = spec["request"]["width"]
    height = spec["request"]["height"]
    with tempfile.TemporaryDirectory(prefix="facet-keyorder-") as root:
        app = Application(root)
        call = http(app)
        plates = keyorder.run(call, spec)
        reading_value = keyorder.reading(plates, spec)
        comparison = keyorder.service_comparison(call, plates)
        reading_value["service_comparison_payload"] = comparison
        for plate in plates:
            for channel, raw in plate["channels"].items():
                writer.write(Path("plates") / "key-order" / (plate["label"] + "-" + channel), raw)
            writer.write(Path("readings") / ("key-order-" + plate["label"] + "-plate.json"),
                         (json.dumps({"plate_id": plate["plate"]["id"],
                                      "seal_id": plate["plate"]["payload"]["seal_id"],
                                      "visual_hash": plate["plate"]["payload"]["visual_hash"],
                                      "objects": plate["plate"]["payload"]["objects"],
                                      "pass_sha256": {channel: sha(raw) for channel, raw
                                                      in plate["channels"].items()}},
                                     indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode())
        writer.write(Path("readings") / "key-order.json",
                     (json.dumps(reading_value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode())
        writer.write(Path("sheets") / "key-order-01-ownership-without-geometry-change.png",
                     keyorder.sheet_png(spec, plates, reading_value, comparison, width, height))
    return {
        "title": spec["title"],
        "question": spec["question"],
        "request": spec["request"],
        "left": reading_value["left"], "right": reading_value["right"],
        "channel_compare": reading_value["channel_compare"],
        "service_comparison": {key: comparison[key] for key in
                               ("color_changed", "mean_channel_delta", "silhouette_changed",
                                "depth_changed", "maximum_depth_delta")},
        "note": "The service comparison endpoint has no object-channel field.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--build-id", default=None)
    arguments = parser.parse_args()
    destination = Path(arguments.output).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit("refusing to write into a nonempty directory")
    destination.mkdir(parents=True, exist_ok=True)
    writer = Writer(destination)

    support = {}
    for name in HARNESS_MODULES:
        raw = (HERE / name).read_bytes()
        support["harness/" + name] = sha(raw)
        writer.write(Path("support") / "harness" / name, raw)
    # Build, verify and drift tools are recorded so the record says how it was
    # produced, but they are excluded from content_digest: they legitimately
    # change between builds of otherwise identical evidence.
    tools = {}
    for name in TOOL_MODULES:
        raw = (HERE / name).read_bytes()
        tools["harness/" + name] = sha(raw)
        writer.write(Path("support") / "tools" / name, raw)
    init_raw = (ROOT / "facetproof" / "__init__.py").read_bytes()
    support["facetproof/__init__.py"] = sha(init_raw)
    writer.write(Path("support") / "facetproof" / "__init__.py", init_raw)
    for name in SERVICE_MODULES:
        raw = (ROOT / "facetproof" / name).read_bytes()
        support["facetproof/" + name] = sha(raw)
        writer.write(Path("support") / "facetproof" / name, raw)
    reader_files = {}
    for name in ("__init__.py", "archive.py", "format.py", "png.py", "errors.py"):
        raw = (ROOT / "facetreader" / name).read_bytes()
        reader_files["facetreader/" + name] = sha(raw)
        writer.write(Path("support") / "facetreader" / name, raw)

    build = {
        "format": "facet-numeric-comparison-bundle-1",
        "build_id": arguments.build_id,
        "renderer_revision": job.RENDERER_REVISION,
        "research_options": variant.RESEARCH_OPTIONS,
        "diagnostic_arms": variant.DIAGNOSTIC_ARMS,
        "support": support,
        "tools": tools,
        "offline_reader": reader_files,
        "scenarios": {},
    }

    for name in SCENARIOS:
        spec = read_spec(name)
        probe = probe_center(spec)
        spec["probe_center"] = probe
        width = spec["request"]["width"]
        height = spec["request"]["height"]
        samples = spec["request"]["samples"]
        with tempfile.TemporaryDirectory(prefix="facet-comparison-") as root:
            result = scenario.submit_scenario(root, spec)
            frozen = job.normalize_input(result["seal"]["payload"], result["plate"]["payload"]["request"])
            frozen["probe_center"] = probe
            job_input = job.frozen_job_from_input(frozen)
            baseline = job.baseline_from_input(frozen)

            replay = variant.render(job_input, variant.BASELINE_OPTIONS)
            if not all(replay[key] == baseline["passes"][key]
                       for key in ("color.rgb", "depth.f32", "object.u32")):
                raise SystemExit("baseline replay from frozen input is not byte-identical")
            if not all(baseline["passes"][key] == result["channels"][key]
                       for key in ("color.rgb", "depth.f32", "object.u32",
                                   "color.png", "depth.png", "object.png")):
                raise SystemExit("frozen input does not reproduce the service plate")

            record = record_scenario(name, spec, frozen, job_input, baseline, result, writer,
                                     width, height, samples, probe)
        build["scenarios"][name] = record
        del result["app"]

    build["companions"] = {"key-order": companion_key_order(writer)}

    # The service assigns random plate, seal and assembly identifiers, so the
    # full build_digest intentionally differs between two builds of the same
    # code and input. content_digest covers only the reproducible material:
    # code digests, frozen inputs, channel bytes, sheet bytes and the counted
    # channel comparisons. Two builds with the same content_digest are
    # equivalent evidence even though their identifiers differ.
    content = {
        "support": support,
        "offline_reader": reader_files,
        "research_options": variant.RESEARCH_OPTIONS,
        "scenarios": {name: {"input_digest": record["input_digest"],
                             "pass_sha256": record["service_plate"]["pass_sha256"],
                             "research_pass_sha256": record["research_pass_sha256"],
                             "against_service": record["against_service"]}
                      for name, record in build["scenarios"].items()},
        "companions": build["companions"],
        "sheets": {relative: descriptor["sha256"] for relative, descriptor in writer.files.items()
                   if relative.startswith("sheets/")},
        "plates": {relative: descriptor["sha256"] for relative, descriptor in writer.files.items()
                   if relative.startswith("plates/")},
    }
    build["content_digest"] = sha(json.dumps(content, sort_keys=True).encode())

    manifest_body = dict(build)
    manifest_body["files"] = writer.files
    manifest_body["build_digest"] = sha(json.dumps(manifest_body, sort_keys=True).encode())
    writer.write(Path("manifest.json"), (json.dumps(manifest_body, indent=2, sort_keys=True,
                                                   ensure_ascii=False) + "\n").encode())
    print(json.dumps({"output": str(destination),
                      "build_digest": manifest_body["build_digest"],
                      "content_digest": manifest_body["content_digest"],
                      "files": len(writer.files)}, indent=2))


def record_scenario(name, spec, frozen, job_input, baseline, result, writer,
                    width, height, samples, probe):
    service = result["channels"]
    input_raw = (json.dumps(frozen, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    writer.write(Path("inputs") / (name + ".json"), input_raw)

    for channel, raw in service.items():
        writer.write(Path("plates") / name / ("service-" + channel), raw)

    readings = {
        "scenario": name,
        "title": spec["title"],
        "question": spec["question"],
        "probe": spec["probe"],
        "input_digest": job.render_input_digest(frozen),
        "service_plate": {
            "plate_id": result["plate"]["id"],
            "visual_hash": result["plate"]["payload"]["visual_hash"],
            "seal_hash": result["plate"]["payload"]["seal_hash"],
            "pass_sha256": {channel: sha(raw) for channel, raw in service.items()},
            "statistics": baseline["statistics"],
            "verification": result["verification"],
        },
        "self_consistency": compare.self_consistency(service, width, height, baseline["plan_objects"]),
        "preview_consistency": compare.preview_consistency(service, width, height, decode_rgb),
        "oracle_service": oracle.check(job_input, service, width, height, samples),
        "arms": {},
    }

    arm_channels_map = {"service": service}
    for arm in variant.DIAGNOSTIC_ARMS:
        if arm in ("baseline", "service"):
            continue
        channels, rendered = arm_channels(frozen, arm, width, height)
        arm_channels_map[arm] = channels
        entry = {
            "options": rendered["options"],
            "covered_pixels": rendered["covered_pixels"],
            "fragments": rendered["fragments"],
            "triangles": rendered["triangles"],
            "against_service": compare.classify(service, channels, width, height),
            "depth_delta_against_service": compare.depth_delta(service, channels, width, height),
            "ownership_transitions": {"%d->%d" % pair: count
                                      for pair, count in compare.ownership_transitions(
                                          service, channels, width, height).items()},
            "self_consistency": compare.self_consistency(channels, width, height,
                                                          baseline["plan_objects"]),
            "oracle": oracle.check(job_input, channels, width, height, samples),
        }
        readings["arms"][arm] = entry
        if arm == "research":
            for channel, raw in channels.items():
                writer.write(Path("plates") / name / ("research-" + channel), raw)

    write_sheets(name, spec, frozen, service, arm_channels_map, writer, width, height, probe,
                 readings, spec["request"]["samples"])
    write_attribution_sheet(name, spec, service, arm_channels_map, readings, writer,
                            width, height)

    writer.write(Path("readings") / (name + ".json"),
                 (json.dumps(readings, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode())
    writer.write(Path("bundles") / (name + ".zip"), result["bundle"])
    offline = validate_bundle(result["bundle"])
    if not offline["valid"]:
        raise SystemExit("offline reader rejected the exported bundle: %s" % offline)

    return {
        "title": spec["title"],
        "question": spec["question"],
        "request": spec["request"],
        "probe": spec["probe"],
        "input": "inputs/%s.json" % name,
        "input_digest": job.render_input_digest(frozen),
        "service_plate": readings["service_plate"],
        "research_pass_sha256": {channel: sha(raw) for channel, raw
                                 in arm_channels_map["research"].items()},
        "against_service": readings["arms"]["research"]["against_service"],
        "offline_reader": {"valid": offline["valid"], "summary": offline["summary"]},
        "research_options": variant.RESEARCH_OPTIONS,
        "arms": {arm: {key: value for key, value in entry.items()
                       if key in ("covered_pixels", "fragments", "triangles")}
                 for arm, entry in readings["arms"].items()},
    }


def write_sheets(name, spec, frozen, service, arm_channels_map, writer, width, height,
                 probe, readings, samples):
    input_digest = readings["input_digest"]
    provenance = ("RENDERER facet-raster-1   INPUT SHA256 %s   SERVICE PLATE %s"
                  % (short(input_digest, 16), short(readings["service_plate"]["visual_hash"], 16)))
    question = font.wrap(spec["question_ascii"], 118)
    research = arm_channels_map["research"]
    research_entry = readings["arms"]["research"]
    against = research_entry["against_service"]
    transitions = research_entry["ownership_transitions"]
    transition_text = ", ".join("%s=%d" % (key, value)
                                for key, value in sorted(transitions.items(),
                                                         key=lambda item: -item[1])[:3]) or "none"
    header = question + [provenance,
                         "RESEARCH VS SERVICE: color-only %d px, ownership-changed %d px (%s), coverage -%d px"
                         % (against["color_only"], against["ownership_changed"],
                            transition_text, against["coverage_lost"]),
                         "SERVICE ORACLE: %s   RESEARCH ORACLE: %s"
                         % (_oracle_summary(readings["oracle_service"]),
                            _oracle_summary(research_entry["oracle"]))]

    color_panels = [
        {"label": "1 SERVICE COLOR (baseline)", "image": (width, height, service["color.rgb"]),
         "note": "covered %d" % readings["service_plate"]["statistics"]["covered_pixels"]},
        {"label": "2 RESEARCH COLOR (variant)", "image": (width, height, research["color.rgb"]),
         "note": "covered %d" % research_entry["covered_pixels"]},
        {"label": "3 OWNERSHIP CHANGE SERVICE -> RESEARCH",
         "image": _raw_map(width, height, pngdiff.ownership_map_rgb(
             width, height, service["object.u32"], research["object.u32"])),
         "note": "yellow changed, blue lost, green gained"},
    ]
    color_panels += [
        {"label": "4 COLOR DELTA SERVICE -> RESEARCH",
         "image": _raw_map(width, height, pngdiff.color_delta_rgb(
             width, height, service["color.rgb"], research["color.rgb"])),
         "note": "grayscale, brighter is larger channel delta"},
        {"label": "5 SERVICE COLOR AT PROBE (x%d)" % probe[0],
         "image": zoom((width, service["color.rgb"]), probe, 16, 8)},
        {"label": "6 RESEARCH COLOR AT PROBE", "image": zoom((width, research["color.rgb"]), probe, 16, 8)},
    ]
    legend = [
        "READ FIRST: a color difference is not an ownership difference. Panels 3 and 4 are separate channels.",
        "Panel 3 uses the object channel only: yellow = same coverage, different owner; blue = coverage lost;",
        "green = coverage gained; dark = identical owner. Panel 4 uses the color channel only.",
        "Transitions are (service object -> research object); full counts in readings/%s.json." % name,
        "Depth-bit changes: %d; see readings/%s.json." % (against["depth_bit_differences"], name),
        "Service: renderer facet-raster-1, pinned in support/facetproof. Research: support/harness/variant.py.",
        "Panels 5-6 are integer nearest-neighbour zooms of the probe window, not smoothed images.",
    ]
    title = "%s - %s" % (spec["id"].upper(), spec["title_ascii"].upper())
    writer.write(Path("sheets") / (name + "-01-color-and-ownership.png"),
                 sheet.render(title, header, color_panels, legend))
    writer.write(Path("readings") / (name + ".sheet1.md"),
                 _sheet_markdown(title, header, [panel["label"] for panel in color_panels], legend).encode())


def _oracle_summary(report):
    if report["agrees"]:
        return "agrees on %d px (%d ambiguous, %d aggregate)" % (
            report["checked_pixels"], report["ambiguous_pixels"], report["aggregate_disagreements"])
    return "DISAGREES: %d ownership, %d depth" % (
        report["ownership_mismatch_count"], report["depth_mismatch_count"])


def write_attribution_sheet(name, spec, service, arm_channels_map, readings, writer,
                            width, height):
    """One row per diagnostic arm: ownership change map plus its counts.

    The grid shows only the object channel, so the sheet answers "which arm
    moves ownership, and in which direction" without inviting color-based
    conclusions. Color deltas live in the per-arm entries of the readings file.
    """
    arm_order = ["reject-near-faces", "average-edge-color", "narrow-tie-window",
                 "perspective-depth", "direct-edges", "divide-barycentrics"]
    panels = []
    header = ["Rows: each diagnostic arm isolates one difference from the service baseline.",
              "Panel: object channel only. Dark = same owner as service, yellow = owner changed,",
              "blue = coverage lost, green = coverage gained. Counts are printed under each label."]
    for arm in arm_order:
        channels = arm_channels_map[arm]
        entry = readings["arms"][arm]
        against = entry["against_service"]
        panels.append({
            "label": arm_label(arm),
            "sublabel": "own %d, color-only %d, lost %d, depth bits %d" % (
                against["ownership_changed"], against["color_only"],
                against["coverage_lost"], against["depth_bit_differences"]),
            "image": _raw_map(width, height, pngdiff.ownership_map_rgb(
                width, height, service["object.u32"], channels["object.u32"])),
        })
    title = "%s - WHICH ARM MOVES OWNERSHIP" % spec["id"].upper()
    writer.write(Path("sheets") / (name + "-02-attribution.png"),
                 sheet.render(title, header, panels, [
                     "Ownership here compares each arm against the service plate of the same frozen input.",
                     "The research arm combines the documented defaults; each other arm reverts exactly one.",
                 ]))
    writer.write(Path("readings") / (name + ".sheet2.md"),
                 _sheet_markdown(title, header, [panel["label"] for panel in panels],
                                 ["Ownership changes against the service plate."]).encode())


def _raw_map(width, height, rgb):
    return width, height, bytes(rgb)


def _sheet_markdown(title, header, labels, legend):
    lines = ["# " + title, "", "Panels, left to right, top to bottom:", ""]
    lines += ["- " + label for label in labels]
    lines += [""] + header + [""] + legend
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
