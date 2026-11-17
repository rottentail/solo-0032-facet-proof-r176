"""Verify a pinned comparison bundle without running any current script.

Usage, from the repository root:

    python3 -I evidence/numeric-variant-comparison/harness/verify.py \
        evidence/numeric-variant-comparison/artifacts/<build-id>

The verifier reads only files inside the bundle directory:

1. ``manifest.json`` is re-hashed and every listed file is checked against its
   recorded SHA-256 and size, so edits after the build are detectable.
2. Each plate is re-derived from the bundle's own ``inputs/`` copy *with the
   variant module copied into ``support/harness/``* - not from the live working
   tree. A mismatch means the recorded plates cannot be explained by the
   recorded input and code.
3. The service plate is re-derived too, using the copied baseline modules in
   ``support/facetproof``. That proves the recorded "service" channels really
   come from the pinned renderer, not from a later edit.
4. Each exported ZIP is re-validated with a copied, independent
   ``facetreader`` that never imports the producer.

Exit status is 0 when every check passes, 2 otherwise. This is a reproduction
check of a pinned record, not a test of the live code base; a live-code change
is supposed to be caught by ``manifest.json`` digests changing, not by this
script silently reinterpreting old plates.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    arguments = parser.parse_args()
    bundle = Path(arguments.bundle).resolve()
    manifest_raw = (bundle / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)

    problems = []
    body = {key: value for key, value in manifest.items() if key not in ("files", "build_digest")}
    body["files"] = manifest["files"]
    recorded = sha(json.dumps(body, sort_keys=True).encode())
    if recorded != manifest["build_digest"]:
        problems.append("manifest digest mismatch")
    for relative, descriptor in manifest["files"].items():
        target = bundle / relative
        if not target.is_file():
            problems.append("missing file: " + relative)
            continue
        raw = target.read_bytes()
        if sha(raw) != descriptor["sha256"] or len(raw) != descriptor["size"]:
            problems.append("content mismatch: " + relative)

    support = bundle / "support"
    with tempfile.TemporaryDirectory(prefix="facet-verify-") as scratch:
        scratch = Path(scratch)
        shutil.copytree(support / "facetproof", scratch / "facetproof")
        reader = scratch / "facetreader"
        shutil.copytree(support / "facetreader", reader)
        sys.path.insert(0, str(scratch))
        for name in list(sys.modules):
            if name.startswith("facetproof") or name.startswith("facetreader"):
                del sys.modules[name]
        import facetreader

        harness = support / "harness"
        for path in harness.glob("*.py"):
            shutil.copy2(path, scratch / ("pinned_" + path.name))
        # The pinned harness modules import each other by their original names;
        # expose the copies under those names so no live file can be loaded.
        for path in harness.glob("*.py"):
            shutil.copy2(path, scratch / path.name)
        variant = load_module("pinned_variant", scratch / "variant.py")
        job = load_module("pinned_job", scratch / "job.py")
        compare = load_module("pinned_compare", scratch / "compare.py")

        for name, record in manifest["scenarios"].items():
            frozen = json.loads((bundle / record["input"]).read_text(encoding="utf-8"))
            baseline = job.baseline_from_input(frozen)
            for channel, expected in record["service_plate"]["pass_sha256"].items():
                raw = (bundle / "plates" / name / ("service-" + channel)).read_bytes()
                if sha(raw) != expected:
                    problems.append("%s: recorded service %s differs from manifest" % (name, channel))
                if baseline["passes"][channel] != raw:
                    problems.append("%s: pinned baseline does not reproduce service %s" % (name, channel))
            rendered = variant.render(job.frozen_job_from_input(frozen),
                                      variant.DIAGNOSTIC_ARMS["research"])
            previews = job.previews(frozen["request"]["width"], frozen["request"]["height"], rendered)
            produced = {"color.rgb": rendered["color.rgb"], "depth.f32": rendered["depth.f32"],
                        "object.u32": rendered["object.u32"], **previews}
            for channel, raw in produced.items():
                stored = (bundle / "plates" / name / ("research-" + channel)).read_bytes()
                if stored != raw:
                    problems.append("%s: pinned variant does not reproduce research %s" % (name, channel))
            readings = json.loads((bundle / "readings" / (name + ".json")).read_text(encoding="utf-8"))
            if readings["input_digest"] != job.render_input_digest(frozen):
                problems.append("%s: input digest does not match the frozen input" % name)
            actual = compare.classify(baseline["passes"], produced,
                                      frozen["request"]["width"], frozen["request"]["height"])
            recorded_against = readings["arms"]["research"]["against_service"]
            for key in ("color_only", "ownership_only", "both", "coverage_lost"):
                if actual[key] != recorded_against[key]:
                    problems.append("%s: %s recorded %d, recomputed %d"
                                    % (name, key, recorded_against[key], actual[key]))
            report = facetreader.validate_bundle((bundle / "bundles" / (name + ".zip")).read_bytes())
            if not report["valid"]:
                problems.append("%s: offline reader rejected bundle" % name)

        companion = manifest.get("companions", {}).get("key-order")
        if companion:
            stored = json.loads((bundle / "readings" / "key-order.json").read_text(encoding="utf-8"))
            sides = {}
            for label in ("left", "right"):
                side = json.loads((bundle / "readings" / ("key-order-" + label + "-plate.json"))
                                  .read_text(encoding="utf-8"))
                channels = {}
                for channel, expected in side["pass_sha256"].items():
                    raw = (bundle / "plates" / "key-order" / (label + "-" + channel)).read_bytes()
                    channels[channel] = raw
                    if sha(raw) != expected:
                        problems.append("key-order/%s: %s differs from recorded hash" % (label, channel))
                sides[label] = channels
            pixels = stored["channel_compare"]["pixels"]
            recomputed = compare.classify(sides["left"], sides["right"], pixels, 1)
            for key in ("color_only", "ownership_only", "both", "coverage_lost"):
                if recomputed[key] != stored["channel_compare"][key]:
                    problems.append("key-order: %s recorded %d, recomputed %d"
                                    % (key, stored["channel_compare"][key], recomputed[key]))

    result = {"bundle": str(bundle), "build_digest": manifest.get("build_digest"),
              "checked_files": len(manifest["files"]), "scenarios": sorted(manifest["scenarios"]),
              "problems": problems, "valid": not problems}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
