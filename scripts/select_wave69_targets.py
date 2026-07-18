#!/usr/bin/env python3
"""Select the preregistered Wave 69 bounded structural targets.

The selector is intentionally tied to one byte-exact, independently replayed
reference atlas.  It does not search for replacement targets when a selected
row is absent or malformed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_PATH = ROOT / "python" / "partizan" / "discovery.py"
ATLAS_SHA256 = "58046bbcbb4644018d4bf31907fcd555220d2bb8e2a5f67607beb6f515883dbf"
ATLAS_GZIP_SHA256 = "471d40092d508e52fcf14d3e292818304fc7cea649c069c96d648ea8deb5ada1"
ATLAS_ROW_COUNT = 108
ATLAS_REPLAY_SHA256 = "bc6de682ffc4fe0f155ef4b130a3edcd3b43595552ed67a664b93621fb5d9a7f"
ATLAS_REPLAY_SUMMARY = {
    "row_count": 108,
    "checked_exact_rows": 108,
    "skipped_rejected_rows": 0,
    "skipped_non_target_rows": 0,
}
REQUIRED_PROOF_KIND = "bitmesh:conservative_legal_independence:v0"
SOURCE_COMMITS = {
    "astralbase": "1434fca1fc04d97798ec1b820c56f52f8014ccc7",
    "bitmesh": "ade3417a007b9c8392d8a153abc4b3ed23edf0aa",
    "partizan": "89c325d52a67bde4d6ac997f4527b7c56a119cf7",
    "thermograph": "1d9b6b01c3921aca8c2a8fb13972fee8a4de5041",
}
ELIGIBLE_FAMILIES = (
    "dfile_two_component_depth2_asymmetric_fan_v0",
    "dfile_two_component_depth2_local_move_v0",
    "dfile_two_component_depth2_pawn_phalanx_v0",
)
EXCLUDED_ROW_NUMBERS = (12, 90)
BIN_COUNT = 6
STAGE_BY_BIN = {
    0: "stage_a",
    1: "stage_b",
    2: "wave_70",
    3: "stage_a",
    4: "stage_b",
    5: "wave_70",
}
POOL_CAP = 4096
VERIFIER_CALL_CAP = 4096
RECURSIVE_NODE_BUDGET = 100000
CHECKED_IN_ATLAS = "data/discovery/wave_69/reference-atlas.jsonl.gz"
CHECKED_IN_REPLAY_ATTESTATION = (
    "data/discovery/wave_69/reference-atlas-replay.json"
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _load_discovery_contract() -> Any:
    spec = importlib.util.spec_from_file_location(
        "partizan_wave69_discovery_contract", DISCOVERY_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load discovery contract from {DISCOVERY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discovery = _load_discovery_contract()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return discovery.canonical_json_bytes(value)


def _fingerprint(value: Any) -> str:
    return sha256_hex(_canonical_bytes(value))


def _read_bound_json(path: Path, expected_sha256: str) -> Any:
    raw = path.read_bytes()
    actual = sha256_hex(raw)
    if actual != expected_sha256:
        raise ValueError(
            f"{path}: SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return json.loads(raw)


def load_bound_atlas(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        compressed_sha256 = sha256_hex(raw)
        if compressed_sha256 != ATLAS_GZIP_SHA256:
            raise ValueError(
                f"{path}: compressed SHA-256 mismatch: expected "
                f"{ATLAS_GZIP_SHA256}, got {compressed_sha256}"
            )
        try:
            atlas_bytes = gzip.decompress(raw)
        except gzip.BadGzipFile as exc:
            raise ValueError(f"{path}: invalid gzip stream") from exc
    else:
        atlas_bytes = raw
    actual = sha256_hex(atlas_bytes)
    if actual != ATLAS_SHA256:
        raise ValueError(
            f"{path}: decompressed SHA-256 mismatch: expected {ATLAS_SHA256}, got {actual}"
        )
    lines = atlas_bytes.splitlines()
    if len(lines) != ATLAS_ROW_COUNT or any(not line.strip() for line in lines):
        raise ValueError(
            f"{path}: expected {ATLAS_ROW_COUNT} nonblank JSONL rows, got {len(lines)}"
        )
    rows = [json.loads(line) for line in lines]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: every JSONL row must be an object")
    return rows


def validate_replay_attestation(path: Path) -> dict[str, Any]:
    value = _read_bound_json(path, ATLAS_REPLAY_SHA256)
    if value != ATLAS_REPLAY_SUMMARY:
        raise ValueError(f"{path}: replay summary does not match the bound summary")
    return value


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{path}: expected a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: expected a positive integer") from exc
    if parsed <= 0 or str(parsed) != str(value):
        raise ValueError(f"{path}: expected a canonical positive integer")
    return parsed


def eligible_records(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_family = {family: [] for family in ELIGIBLE_FAMILIES}
    seen_row_ids: set[str] = set()
    seen_identities: set[str] = set()
    for source_index, row in enumerate(rows):
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or not row_id:
            raise ValueError(f"atlas[{source_index}].row_id: expected nonempty string")
        if row_id in seen_row_ids:
            raise ValueError(f"atlas[{source_index}].row_id: duplicate {row_id}")
        seen_row_ids.add(row_id)

        exact = row.get("exact")
        value = exact.get("value") if isinstance(exact, dict) else None
        if not isinstance(value, dict):
            continue
        row_number = _positive_int(value.get("row_number"), f"{row_id}.row_number")
        if row_number in EXCLUDED_ROW_NUMBERS:
            continue
        family = value.get("component_topology_family")
        if family not in by_family:
            continue
        if row.get("label_kind") != "exact" or exact.get("status") != "verified":
            continue
        if str(value.get("component_count")) != "2":
            continue
        if value.get("proof_kind") != REQUIRED_PROOF_KIND:
            raise ValueError(
                f"{row_id}: unsupported conservative decomposition proof kind"
            )
        identity = value.get("result_digest_v1_sha256")
        if not isinstance(identity, str) or HEX64.fullmatch(identity) is None:
            continue
        if identity in seen_identities:
            raise ValueError(f"{row_id}: duplicate structural identity {identity}")
        seen_identities.add(identity)
        nodes = _positive_int(
            value.get("component_recursive_total_nodes"),
            f"{row_id}.component_recursive_total_nodes",
        )
        if value.get("composition_value_rule") != discovery.VALUE_RULE:
            raise ValueError(f"{row_id}: unsupported bounded value rule")
        if value.get("value_class") != "game_tree":
            raise ValueError(f"{row_id}: unsupported value class")
        if row.get("domain") != "formal_domain:bitmesh_composed_board_material:v0":
            raise ValueError(f"{row_id}: unsupported formal domain")
        position = row.get("position")
        if not isinstance(position, dict) or position.get("encoding") != "fen":
            raise ValueError(f"{row_id}: missing FEN position")
        fen = position.get("text")
        if not isinstance(fen, str) or len(fen.split()) != 6:
            raise ValueError(f"{row_id}: position is not a six-field FEN string")
        provenance = row.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("code_commit") != SOURCE_COMMITS["astralbase"]:
            raise ValueError(f"{row_id}: Astralbase source commit does not match boundary")
        by_family[family].append(
            {
                "domain": row["domain"],
                "family": family,
                "fen": fen,
                "identity_sha256": identity,
                "recursive_nodes": nodes,
                "row_id": row_id,
                "row_number": row_number,
                "value_class": value["value_class"],
                "value_rule": value["composition_value_rule"],
            }
        )

    for family, records in by_family.items():
        if len(records) < BIN_COUNT:
            raise ValueError(
                f"{family}: {len(records)} eligible rows cannot fill {BIN_COUNT} bins; "
                "substitution is forbidden"
            )
        records.sort(
            key=lambda item: (
                item["recursive_nodes"],
                item["identity_sha256"],
                item["row_id"],
            )
        )
    return by_family


def contiguous_balanced_bins(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    quotient, remainder = divmod(len(records), BIN_COUNT)
    sizes = [quotient + (1 if index < remainder else 0) for index in range(BIN_COUNT)]
    bins: list[list[dict[str, Any]]] = []
    start = 0
    for size in sizes:
        bins.append(records[start : start + size])
        start += size
    if start != len(records) or any(not bin_rows for bin_rows in bins):
        raise ValueError("cannot construct six nonempty contiguous balanced bins")
    return bins


def _target_spec(record: dict[str, Any]) -> dict[str, Any]:
    target = {
        "domain": record["domain"],
        "position_constraints": {
            "castling_rights": "none",
            "en_passant": "none",
            "encoding": "fen",
            "legality_contract": discovery.LEGALITY_CONTRACT,
        },
        "provenance": {
            "source_artifact": CHECKED_IN_ATLAS,
            "source_commit": SOURCE_COMMITS["astralbase"],
            "source_row_id": record["row_id"],
        },
        "ranker_view": {
            "identity_contract": discovery.IDENTITY_CONTRACT,
            "identity_sha256": record["identity_sha256"],
            "kind": discovery.TARGET_KIND,
            "value_class": record["value_class"],
            "value_rule": record["value_rule"],
        },
        "schema_version": discovery.TARGET_SCHEMA_VERSION,
        "search_limits": {
            "max_pool_size": POOL_CAP,
            "max_recursive_nodes_per_candidate": RECURSIVE_NODE_BUDGET,
            "max_verifier_calls": VERIFIER_CALL_CAP,
        },
        "target": {
            "equality_scope": discovery.IDENTITY_SCOPE,
            "identity_contract": discovery.IDENTITY_CONTRACT,
            "identity_sha256": record["identity_sha256"],
            "kind": discovery.TARGET_KIND,
            "value_class": record["value_class"],
            "value_rule": record["value_rule"],
        },
    }
    target["target_id"] = discovery.target_id_for(target)
    errors = discovery.validate_target_spec(target)
    if errors:
        raise ValueError(f"{record['row_id']}: invalid target contract: {'; '.join(errors)}")
    return target


def _source_boundary() -> dict[str, Any]:
    return {
        "atlas": {
            "availability": "checked_in_compressed",
            "compressed_sha256": ATLAS_GZIP_SHA256,
            "decompressed_sha256": ATLAS_SHA256,
            "path": CHECKED_IN_ATLAS,
            "row_count": ATLAS_ROW_COUNT,
        },
        "clean_source_commits": SOURCE_COMMITS,
        "replay_attestation": {
            "availability": "checked_in",
            "path": CHECKED_IN_REPLAY_ATTESTATION,
            "sha256": ATLAS_REPLAY_SHA256,
            "summary": ATLAS_REPLAY_SUMMARY,
        },
    }


def build_registry(
    atlas_path: Path, replay_attestation_path: Path
) -> dict[str, Any]:
    rows = load_bound_atlas(atlas_path)
    validate_replay_attestation(replay_attestation_path)
    by_family = eligible_records(rows)
    source_boundary = _source_boundary()
    source_boundary_sha256 = _fingerprint(source_boundary)
    targets: list[dict[str, Any]] = []

    for family in ELIGIBLE_FAMILIES:
        bins = contiguous_balanced_bins(by_family[family])
        offset = 0
        for bin_index, bin_rows in enumerate(bins):
            stage = STAGE_BY_BIN[bin_index]
            selected = min(
                bin_rows,
                key=lambda item: (item["identity_sha256"], item["row_id"]),
            )
            member_projection = [
                {
                    "identity_sha256": item["identity_sha256"],
                    "recursive_nodes": item["recursive_nodes"],
                    "row_id": item["row_id"],
                }
                for item in bin_rows
            ]
            bin_members_sha256 = _fingerprint(member_projection)
            selection_payload = {
                "atlas_compressed_sha256": ATLAS_GZIP_SHA256,
                "atlas_decompressed_sha256": ATLAS_SHA256,
                "bin_index": bin_index,
                "bin_members_sha256": bin_members_sha256,
                "family": family,
                "selected_identity_sha256": selected["identity_sha256"],
                "selected_row_id": selected["row_id"],
                "source_boundary_sha256": source_boundary_sha256,
                "stage": stage,
            }
            targets.append(
                {
                    "bin": {
                        "index": bin_index,
                        "size": len(bin_rows),
                        "sorted_start_inclusive": offset,
                        "sorted_stop_exclusive": offset + len(bin_rows),
                        "member_projection_sha256": bin_members_sha256,
                    },
                    "family": family,
                    "selection_sha256": _fingerprint(selection_payload),
                    "source_boundary_sha256": source_boundary_sha256,
                    "source_row": {
                        "fen": selected["fen"],
                        "fen_sha256": sha256_hex(selected["fen"].encode("utf-8")),
                        "identity_sha256": selected["identity_sha256"],
                        "recursive_nodes": selected["recursive_nodes"],
                        "row_id": selected["row_id"],
                        "row_number": selected["row_number"],
                    },
                    "stage": stage,
                    "target_spec": _target_spec(selected),
                }
            )
            offset += len(bin_rows)

    registry = {
        "registry_id": "",
        "schema_version": "partizan.wave69_target_registry.v0.1",
        "source_boundary": source_boundary,
        "source_boundary_sha256": source_boundary_sha256,
        "selection_contract": {
            "bin_count_per_family": BIN_COUNT,
            "bin_partition": "contiguous_size_balanced_first_remainder_bins_larger_v0",
            "eligibility": {
                "component_count": 2,
                "exact_status": "verified",
                "identity": "result_digest_v1_sha256_lowercase_hex64",
                "label_kind": "exact",
                "proof_kind": REQUIRED_PROOF_KIND,
                "topology_families": list(ELIGIBLE_FAMILIES),
            },
            "excluded_source_row_numbers": list(EXCLUDED_ROW_NUMBERS),
            "selection_within_bin": "minimum_identity_sha256_then_row_id_v0",
            "sort_within_family": [
                "component_recursive_total_nodes_integer_ascending",
                "result_digest_v1_sha256_ascending",
                "row_id_ascending",
            ],
            "stage_by_bin": {str(key): value for key, value in STAGE_BY_BIN.items()},
            "substitution_policy": "forbidden",
        },
        "target_count": len(targets),
        "targets": targets,
    }
    registry_payload = dict(registry)
    registry_payload.pop("registry_id")
    registry["registry_id"] = f"registry-sha256:{_fingerprint(registry_payload)}"
    if len(targets) != len(ELIGIBLE_FAMILIES) * BIN_COUNT:
        raise ValueError("registry must contain exactly 18 targets")
    return registry


def render_report(registry: dict[str, Any]) -> str:
    boundary = registry["source_boundary"]
    lines = [
        "# Wave 69 target-registry selection report",
        "",
        "Status: preregistered target selection, not publication evidence.",
        "",
        "The clean reference atlas is checked in as a byte-exact gzip artifact. Its replay",
        "replay attestation is checked in beside it. Selection is accepted only for the",
        "bound atlas and attestation hashes below; a missing selected row is not replaced.",
        "",
        "## Source boundary",
        "",
        f"- Checked-in atlas: `{boundary['atlas']['path']}` ({boundary['atlas']['row_count']} rows)",
        f"- Compressed atlas SHA-256: `{boundary['atlas']['compressed_sha256']}`",
        f"- Decompressed atlas SHA-256: `{boundary['atlas']['decompressed_sha256']}`",
        f"- Replay-attestation SHA-256: `{boundary['replay_attestation']['sha256']}`",
        f"- Checked-in replay attestation: `{boundary['replay_attestation']['path']}`",
        f"- Source-boundary SHA-256: `{registry['source_boundary_sha256']}`",
        f"- Registry ID: `{registry['registry_id']}`",
        "- Replay summary: 108 exact rows checked; zero rejected or non-target rows skipped.",
        "",
        "Clean commits: "
        + ", ".join(
            f"{name} `{commit}`"
            for name, commit in boundary["clean_source_commits"].items()
        )
        + ".",
        "",
        "## Frozen rule",
        "",
        "Rows 012 and 090 are excluded. Eligible rows must be exact/verified, carry a",
        "lowercase SHA-256 structural identity, have exactly two components certified by",
        f"`{REQUIRED_PROOF_KIND}`, and belong to one of the three named topology families.",
        "Each family is sorted by recursive",
        "nodes, identity, then row ID; split into six contiguous size-balanced bins; and",
        "the smallest identity in each bin is selected. Bins 0/3 are Stage A, 1/4 are",
        "Stage B, and 2/5 are reserved for Wave 70. Substitution is forbidden.",
        "",
        "Every target contract fixes a pool cap of 4096, 4096 verifier calls, and a",
        "100000-node per-candidate budget.",
        "",
        "## Selected targets",
        "",
        "| Family | Bin | Stage | Row | Nodes | Structural identity | Selection SHA-256 |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for item in registry["targets"]:
        row = item["source_row"]
        lines.append(
            f"| `{item['family']}` | {item['bin']['index']} | `{item['stage']}` | "
            f"{row['row_number']:03d} | {row['recursive_nodes']} | "
            f"`{row['identity_sha256']}` | `{item['selection_sha256']}` |"
        )
    lines.extend(
        [
            "",
            "## Replay",
            "",
            "```bash",
            "python3 scripts/select_wave69_targets.py \\",
            "  --atlas data/discovery/wave_69/reference-atlas.jsonl.gz \\",
            "  --check",
            "```",
            "",
            "The command verifies the checked-in compressed and decompressed atlas hashes,",
            "plus the checked-in replay-attestation hash, before recomputing both artifacts.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_or_check(path: Path, expected: bytes, check: bool) -> None:
    if check:
        if not path.exists():
            raise ValueError(f"{path}: missing generated artifact")
        actual = path.read_bytes()
        if actual != expected:
            raise ValueError(f"{path}: generated artifact is stale")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument(
        "--replay-attestation",
        type=Path,
        default=ROOT / CHECKED_IN_REPLAY_ATTESTATION,
    )
    parser.add_argument(
        "--registry-out",
        type=Path,
        default=ROOT / "docs" / "discovery_targets" / "wave_69_target_registry.v0.1.json",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=ROOT / "docs" / "discovery_wave_69_target_selection_report.md",
    )
    parser.add_argument(
        "--check", action="store_true", help="compare with generated artifacts without writing"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        registry = build_registry(args.atlas, args.replay_attestation)
        report = render_report(registry).encode("utf-8")
        _write_or_check(args.registry_out, _canonical_bytes(registry), args.check)
        _write_or_check(args.report_out, report, args.check)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"wave69 target selection failed: {exc}", file=sys.stderr)
        return 1
    action = "validated" if args.check else "generated"
    print(
        f"{action} {registry['target_count']} targets; {registry['registry_id']}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
