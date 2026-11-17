"""Report live-tree differences against a pinned bundle.

    python3 -I evidence/numeric-variant-comparison/harness/drift.py \
        evidence/numeric-variant-comparison/artifacts/<build-id>

This never edits the bundle and never reinterprets its plates. It answers one
question only: does the code in the working tree still match the code that
produced the pinned evidence? A difference means later edits happened; the
pinned bundle still means exactly what it meant when it was built.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
EVIDENCE = ROOT / "evidence" / "numeric-variant-comparison"


def live_path(relative):
    if relative.startswith("harness/"):
        return EVIDENCE / relative
    return ROOT / relative


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    arguments = parser.parse_args()
    bundle = Path(arguments.bundle).resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    changes = []
    for relative, expected in sorted(manifest["support"].items()):
        path = live_path(relative)
        if not path.is_file():
            changes.append({"module": relative, "status": "missing"})
            continue
        actual = sha(path.read_bytes())
        if actual != expected:
            changes.append({"module": relative, "status": "changed",
                            "pinned": expected, "live": actual})
    for relative, expected in sorted(manifest.get("offline_reader", {}).items()):
        path = live_path(relative)
        actual = sha(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            changes.append({"module": relative, "status": "changed" if actual else "missing",
                            "pinned": expected, "live": actual})
    for relative, expected in sorted(manifest.get("tools", {}).items()):
        path = live_path(relative)
        actual = sha(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            changes.append({"module": relative, "status": "changed" if actual else "missing",
                            "pinned": expected, "live": actual,
                            "scope": "tooling only; excluded from content_digest"})
    report = {"bundle": str(bundle), "build_digest": manifest["build_digest"],
              "live_matches_pinned": not changes, "differences": changes,
              "meaning": ("Pinned plates keep the meaning recorded at build time. "
                          "These differences describe the live tree only.")}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not changes else 1


if __name__ == "__main__":
    sys.exit(main())
