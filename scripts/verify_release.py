#!/usr/bin/env python3
"""Verify Partizan's frozen v0.1 P01/P02 artifacts and required claim boundaries.

Scope: this checks only the artifacts listed in
``data/research-v0.1/manifest.json`` (the reproducible vertical slice and the
P02 representative dataset) plus deterministic event bytes. It does not
verify the Wave 69 / 69-R discovery evidence under ``data/discovery/``; those
waves have their own ``--check-only`` entry points
(``scripts/freeze_wave69_stage_a_suite.py``,
``python/partizan/wave69r_gate_c_suite.py``,
``python/partizan/wave69r_gate_c_evidence.py``) and are not release-complete
artifacts (see ``docs/release_blockers.md``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

import label_schema  # noqa: E402


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    """Raise a stable verification failure when a condition is false."""

    if not condition:
        raise RuntimeError(message)


def verify_manifest() -> None:
    """Verify artifact bytes, row schema, P02 fields, and report linkage."""

    manifest_path = ROOT / "data" / "research-v0.1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        require(path.is_file(), f"missing frozen artifact: {artifact['path']}")
        require(
            sha256(path) == artifact["sha256"],
            f"SHA-256 mismatch: {artifact['path']}",
        )

    artifacts = {artifact["role"]: artifact for artifact in manifest["artifacts"]}
    vertical_slice = ROOT / artifacts["reproducible_vertical_slice"]["path"]
    vertical_issues = label_schema.validate_jsonl(vertical_slice)
    require(
        not vertical_issues,
        f"vertical-slice schema issues: {[item.format() for item in vertical_issues]}",
    )
    vertical_rows = [
        json.loads(line)
        for line in vertical_slice.read_text(encoding="utf-8").splitlines()
    ]
    require(len(vertical_rows) == 5, "vertical slice must contain 5 rows")
    require(
        [row["label_kind"] for row in vertical_rows].count("exact") == 3,
        "vertical slice must contain 3 exact rows",
    )
    require(
        [row["label_kind"] for row in vertical_rows].count("rejected") == 2,
        "vertical slice must contain 2 rejected rows",
    )
    for row in vertical_rows:
        if row["label_kind"] == "exact":
            require(
                row["provenance"]["code_commit"]
                == manifest["generator_config"]["source_commit"],
                "vertical-slice source commit is not frozen",
            )

    dataset_artifact = artifacts["historical_exact_metadata_slice"]
    dataset = ROOT / dataset_artifact["path"]
    issues = label_schema.validate_jsonl(dataset)
    require(not issues, f"dataset schema issues: {[item.format() for item in issues]}")
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    require(len(rows) == 13, "representative dataset must contain 13 rows")
    require(all(row.get("label_kind") == "exact" for row in rows), "all rows must be exact")
    for row in rows:
        certificate = row["provenance"]["certificate"]
        require(bool(certificate.get("decomposition_digest")), "P02 decomposition digest absent")
        require(bool(certificate.get("component_values")), "P02 component values absent")
        require(bool(certificate.get("result_value_digest")), "P02 result digest absent")

    corrupted = json.loads(json.dumps(rows[0]))
    del corrupted["provenance"]["certificate"]["result_value_digest"]
    require(
        any("result_value_digest" in issue for issue in label_schema.validate_row(corrupted)),
        "P02 corruption control unexpectedly passed",
    )
    split_report = json.loads(
        (ROOT / "docs" / "signature_target_exact_wave_47_split_report.json").read_text(
            encoding="utf-8"
        )
    )
    require(
        split_report.get("dataset_sha256") == dataset_artifact["sha256"],
        "split report does not bind the frozen dataset",
    )


def verify_events() -> None:
    """Verify deterministic Partizan event bytes through the installed package."""

    import partizan

    fen = "7k/5KQ1/8/8/8/8/8/8 b - - 0 1"
    first = partizan.canonical_event_bytes(partizan.build_event_stream(fen))
    second = partizan.canonical_event_bytes(partizan.build_event_stream(fen))
    require(first == second, "event stream is not byte-identical across runs")
    require(not partizan.validate_event_stream(json.loads(first)), "event stream is invalid")


def main() -> int:
    """Run all release verifications."""

    try:
        verify_manifest()
        verify_events()
    except (
        ImportError,
        IndexError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(f"release verification: failed: {error}", file=sys.stderr)
        return 1
    print(
        "P01/P02 release verification: ok "
        "(5 artifacts, 5-row reproducible slice, 13-row P02 slice, events; "
        "Wave 69/69-R discovery evidence is out of scope, see docs/release_blockers.md)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
