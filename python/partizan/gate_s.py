"""Target-free orchestration for the Wave 69-R structural supply gate.

The module projects strict candidate-board-stream rows to the two fields used
by the native checker.  It has no target, Astralbase, Thermograph, evaluator,
ranker, or result-label interface.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
CHECKER_MANIFEST = ROOT / "engine/gate_s_checker/Cargo.toml"
CHECKER_LOCK = ROOT / "engine/gate_s_checker/Cargo.lock"
CHECKER_SOURCE = ROOT / "engine/gate_s_checker/src/main.rs"
CHECKER_WRAPPER = ROOT / "python/partizan/gate_s.py"
REQUEST_SCHEMA = "partizan.wave69r_structural_supply_request.v0.1"
RESULT_SCHEMA = "partizan.wave69r_structural_supply_result.v0.1"
EVIDENCE_SCHEMA = "partizan.wave69r_structural_supply_evidence.v0.1"
SUPPLY_SUITE_SCHEMA = "partizan.wave69r_structural_supply_suite.v0.1"
SUPPLY_SHARD_MANIFEST_SCHEMA = "partizan.wave69r_supply_shard_manifest.v0.1"
SUPPLY_CERTIFICATE_SCHEMA = "partizan.structural_construction_certificate.v0.1"
BOARD_STREAM_SCHEMA = "partizan.candidate_board_stream.v0.1"
ASTRALBASE_COMMIT = "1434fca1fc04d97798ec1b820c56f52f8014ccc7"
BITMESH_COMMIT = "ade3417a007b9c8392d8a153abc4b3ed23edf0aa"
THERMOGRAPH_COMMIT = "1d9b6b01c3921aca8c2a8fb13972fee8a4de5041"
BITMESH_CRATE_VERSION = "0.1.0"
CHECKER_NAME = "partizan_gate_s_checker"
CHECKER_VERSION = "0.1.0"
PROOF_API = "bitmesh:conservative_legal_independence:v0"
GATE_S_ROW_COUNT = 4096
SUPPLY_INPUT_ROOT = "data/discovery/wave_69r/structural_supply/inputs"
SUPPLY_FREEZE_DOCUMENT = "docs/discovery_wave_69r_structural_supply_freeze.md"
EVIDENCE_PRIMARY_PATH = (
    "data/discovery/wave_69r/structural_supply/evidence/primary.jsonl"
)
EVIDENCE_REPLAY_PATH = (
    "data/discovery/wave_69r/structural_supply/evidence/replay.jsonl"
)
EVIDENCE_MANIFEST_PATH = (
    "data/discovery/wave_69r/structural_supply/evidence/evidence.json"
)
EVIDENCE_AUDIT_DOCUMENTS = (
    "docs/discovery_wave_69r_structural_supply_audit.md",
    "docs/discovery_wave_69r_structural_supply_audit.v0.1.json",
)
EVIDENCE_COMMIT_PATHS = (
    EVIDENCE_PRIMARY_PATH,
    EVIDENCE_REPLAY_PATH,
    EVIDENCE_MANIFEST_PATH,
    *EVIDENCE_AUDIT_DOCUMENTS,
)
EVIDENCE_VALIDATOR_DEPENDENCIES = (
    "python/partizan/gate_s.py",
    "python/partizan/wave69r_supply.py",
    "python/partizan/discovery.py",
    "engine/orchestrator.py",
    "docs/discovery_wave_69r_construction_catalog.v0.2.json",
)

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TYPED_BOARD_ID = re.compile(r"^board-sha256:[0-9a-f]{64}$")
TYPED_TEMPLATE_ID = re.compile(r"^template-sha256:[0-9a-f]{64}$")
TYPED_EVIDENCE_ID = re.compile(r"^evidence-sha256:[0-9a-f]{64}$")
BOARD_FIELD = re.compile(r"^(?:[1-8pnbrqkPNBRQK]+/){7}[1-8pnbrqkPNBRQK]+$")

_BOARD_ROW_KEYS = {
    "schema_version",
    "board_id",
    "ordinal",
    "position",
    "generator",
    "construction",
    "proposal_features",
}
_REQUEST_KEYS = {"schema_version", "board_id", "board_fen"}
_RESULT_KEYS = {
    "schema_version",
    "board_id",
    "checker",
    "outcome",
    "certification",
    "failure_code",
    "predicates",
    "internal_error",
}
_PREDICATE_KEYS = {
    "frozen_barrier",
    "non_capturable_barrier",
    "strict_exactly_two_components",
    "no_cross_component_entry",
}
_PREDICATE_STATES = {"pass", "fail", "not_evaluated"}
_FAILURE_CODES = {
    "input.invalid_board_fen",
    "checker.internal_error",
    "structure.component_count_not_two",
    "bitmesh.requires_strict_decomposition",
    "bitmesh.barrier_square_is_empty",
    "bitmesh.barrier_square_is_not_pawn",
    "bitmesh.barrier_pawn_not_frozen",
    "bitmesh.barrier_pawn_can_capture",
    "bitmesh.active_piece_outside_certified_component",
    "bitmesh.barrier_piece_can_be_captured",
    "bitmesh.piece_can_enter_other_component",
    "bitmesh.piece_can_enter_uncertified_free_square",
    "bitmesh.invalid_certificate.strict_status_mismatch",
    "bitmesh.invalid_certificate.component_intersects_barrier",
    "bitmesh.invalid_certificate.active_mask_outside_component",
    "bitmesh.invalid_certificate.active_component_count_mismatch",
    "bitmesh.invalid_certificate.strict_with_too_few_active_components",
    "bitmesh.invalid_certificate.strict_without_barrier",
    "bitmesh.invalid_certificate.strict_with_rejection_reason",
    "bitmesh.invalid_certificate.rejected_without_rejection_reason",
    "bitmesh.invalid_certificate.no_locked_barrier_rejection_with_barrier",
    "bitmesh.invalid_certificate.no_locked_barrier_rejection_with_multiple_active_components",
    "bitmesh.invalid_certificate.less_than_two_active_components_rejection_without_barrier",
    "bitmesh.invalid_certificate.less_than_two_active_components_rejection_with_too_many_active_components",
    "bitmesh.invalid_certificate.empty_component_mask",
    "bitmesh.invalid_certificate.component_without_active_squares",
    "bitmesh.invalid_certificate.component_root_outside_mask",
    "bitmesh.invalid_certificate.component_masks_overlap",
    "bitmesh.invalid_certificate.duplicate_component_root",
    "bitmesh.invalid_certificate.cross_component_adjacency",
    "bitmesh.invalid_certificate.strict_component_mask_not_closed",
}


class GateSContractError(ValueError):
    """Raised before any checker invocation when a Gate S contract fails."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact_mapping(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateSContractError(f"{path}: must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise GateSContractError(
            f"{path}: keys differ (missing={missing}, unknown={extra})"
        )
    return value


def _require_hex(value: Any, pattern: re.Pattern[str], path: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise GateSContractError(f"{path}: invalid lowercase hexadecimal identity")
    return value


def _fen_state_without_clocks(fen: str) -> str:
    fields = fen.split()
    if len(fields) != 6:
        raise GateSContractError("position.text: must contain exactly six FEN fields")
    if fields[1:] != ["w", "-", "-", "0", "1"]:
        raise GateSContractError("position.text: metadata must be exactly 'w - - 0 1'")
    return " ".join(fields[:4])


def _board_id_for_fen(fen: str) -> str:
    identity = {
        "position_state": {
            "encoding": "fen",
            "text_without_move_clocks": _fen_state_without_clocks(fen),
        }
    }
    digest = hashlib.sha256(
        (
            json.dumps(
                identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    return f"board-sha256:{digest}"


def _reflect_fen_files(fen: str) -> str:
    fields = _fen_state_without_clocks(fen).split()
    reflected_ranks: list[str] = []
    for encoded_rank in fields[0].split("/"):
        expanded: list[str] = []
        for token in encoded_rank:
            if token.isdigit():
                expanded.extend("." for _ in range(int(token)))
            else:
                expanded.append(token)
        if len(expanded) != 8:
            raise GateSContractError("position.text: each rank must expand to eight files")
        reflected: list[str] = []
        empty = 0
        for token in reversed(expanded):
            if token == ".":
                empty += 1
            else:
                if empty:
                    reflected.append(str(empty))
                    empty = 0
                reflected.append(token)
        if empty:
            reflected.append(str(empty))
        reflected_ranks.append("".join(reflected))
    if len(reflected_ranks) != 8:
        raise GateSContractError("position.text: board must contain eight ranks")
    fields[0] = "/".join(reflected_ranks)
    return " ".join(fields)


def _reflection_sha256(fen: str) -> str:
    state = _fen_state_without_clocks(fen)
    return sha256_hex(min(state, _reflect_fen_files(fen)).encode("utf-8"))


def _expected_features(fen: str) -> dict[str, Any]:
    board = fen.split()[0]
    squares: dict[str, str] = {}
    pieces: list[str] = []
    for rank, encoded in zip(range(8, 0, -1), board.split("/")):
        file_index = 0
        for token in encoded:
            if token.isdigit():
                file_index += int(token)
            else:
                if file_index >= 8:
                    raise GateSContractError("position.text: rank expands beyond eight files")
                squares[f"{'abcdefgh'[file_index]}{rank}"] = token
                pieces.append(token)
                file_index += 1
        if file_index != 8:
            raise GateSContractError("position.text: each rank must expand to eight files")
    occupied_files = {square[0] for square in squares}
    backbone = {f"d{rank}": "P" if rank % 2 else "p" for rank in range(1, 9)}
    return {
        "schema_version": "partizan.proposal_features.v0.1",
        "derivation_stage": "pre_verification",
        "categorical": {},
        "integer": {
            "black_piece_count": sum(piece.islower() for piece in pieces),
            "non_pawn_piece_count": sum(piece.upper() != "P" for piece in pieces),
            "occupied_file_count": len(occupied_files),
            "pawn_count": sum(piece.upper() == "P" for piece in pieces),
            "piece_count": len(pieces),
            "white_piece_count": sum(piece.isupper() for piece in pieces),
        },
        "boolean": {
            "has_locked_d_file_backbone": all(
                squares.get(square) == piece for square, piece in backbone.items()
            )
        },
    }


def validate_board_stream_row(value: Any) -> dict[str, Any]:
    row = _exact_mapping(value, _BOARD_ROW_KEYS, "board_stream")
    if row["schema_version"] != BOARD_STREAM_SCHEMA:
        raise GateSContractError("board_stream.schema_version: unsupported")
    _require_hex(row["board_id"], TYPED_BOARD_ID, "board_stream.board_id")
    ordinal = row["ordinal"]
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        raise GateSContractError("board_stream.ordinal: must be non-negative integer")

    position = _exact_mapping(
        row["position"], {"encoding", "text", "sha256", "symmetry_sha256"}, "position"
    )
    if position["encoding"] != "fen" or not isinstance(position["text"], str):
        raise GateSContractError("position: must contain a FEN string")
    fen = position["text"]
    board_fen = _fen_state_without_clocks(fen).split()[0]
    if BOARD_FIELD.fullmatch(board_fen) is None:
        raise GateSContractError("position.text: invalid board-field character grammar")
    if position["sha256"] != sha256_hex(fen.encode("utf-8")):
        raise GateSContractError("position.sha256: does not bind position.text")
    if position["symmetry_sha256"] != _reflection_sha256(fen):
        raise GateSContractError("position.symmetry_sha256: does not bind reflection orbit")
    if row["board_id"] != _board_id_for_fen(fen):
        raise GateSContractError("board_stream.board_id: does not bind clock-free FEN")

    generator = _exact_mapping(
        row["generator"],
        {
            "name",
            "version",
            "code_commit",
            "family",
            "operator",
            "config_sha256",
            "random_seed",
        },
        "generator",
    )
    expected_generator = {
        "name": "partizan_candidate_pool_generator",
        "version": "0.2.0",
        "family": "dfile_two_component_constructive_grammar_v2",
        "operator": "seeded_constructive_component_composition_v2",
    }
    for key, expected in expected_generator.items():
        if generator[key] != expected:
            raise GateSContractError(f"generator.{key}: expected {expected}")
    _require_hex(generator["code_commit"], HEX40, "generator.code_commit")
    _require_hex(generator["config_sha256"], HEX64, "generator.config_sha256")
    seed = generator["random_seed"]
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise GateSContractError("generator.random_seed: must be non-negative integer")

    construction = _exact_mapping(
        row["construction"],
        {
            "contract",
            "stratum",
            "left_active_piece_count",
            "right_active_piece_count",
            "left_template_id",
            "right_template_id",
            "runtime_oracle_used",
        },
        "construction",
    )
    if construction["contract"] != "partizan.dfile_two_component_constructive_grammar.v0.2":
        raise GateSContractError("construction.contract: unsupported")
    if construction["stratum"] not in {
        "outer_leaper",
        "pawn_phalanx",
        "ray_cage",
        "mixed_color_hook",
    }:
        raise GateSContractError("construction.stratum: unsupported")
    for key in ("left_active_piece_count", "right_active_piece_count"):
        count = construction[key]
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 5:
            raise GateSContractError(f"construction.{key}: must be from 1 through 5")
    for key in ("left_template_id", "right_template_id"):
        _require_hex(construction[key], TYPED_TEMPLATE_ID, f"construction.{key}")
    if construction["runtime_oracle_used"] is not False:
        raise GateSContractError("construction.runtime_oracle_used: must be false")
    if row["proposal_features"] != _expected_features(fen):
        raise GateSContractError("proposal_features: not the exact seven pre-verification features")
    return row


def project_request(board_row: Any) -> dict[str, Any]:
    row = validate_board_stream_row(board_row)
    return {
        "schema_version": REQUEST_SCHEMA,
        "board_id": row["board_id"],
        "board_fen": row["position"]["text"].split()[0],
    }


def validate_request(value: Any) -> dict[str, Any]:
    row = _exact_mapping(value, _REQUEST_KEYS, "request")
    if row["schema_version"] != REQUEST_SCHEMA:
        raise GateSContractError("request.schema_version: unsupported")
    _require_hex(row["board_id"], TYPED_BOARD_ID, "request.board_id")
    if not isinstance(row["board_fen"], str) or BOARD_FIELD.fullmatch(row["board_fen"]) is None:
        raise GateSContractError("request.board_fen: must be only one FEN board field")
    expected_board_id = _board_id_for_fen(f'{row["board_fen"]} w - - 0 1')
    if row["board_id"] != expected_board_id:
        raise GateSContractError("request.board_id: does not bind board_fen")
    return row


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return _load_jsonl_text(path.read_text(encoding="utf-8"), str(path))


def _load_jsonl_text(text: str, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line:
            raise GateSContractError(f"{source}:{line_number}: blank rows are forbidden")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise GateSContractError(f"{source}:{line_number}: invalid JSON: {error}") from error
        if not isinstance(value, dict):
            raise GateSContractError(f"{source}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    os.replace(temporary, path)


def _relative_artifact_path(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).is_absolute()
        or "\\" in value
        or ".." in Path(value).parts
    ):
        raise GateSContractError(f"{path}: must be a repository-relative path")
    return value


def _artifact_path(repository_root: Path, reference: dict[str, Any], path: str) -> Path:
    relative = _relative_artifact_path(reference.get("path"), f"{path}.path")
    root = repository_root.resolve()
    artifact = (root / relative).resolve()
    try:
        artifact.relative_to(root)
    except ValueError as error:
        raise GateSContractError(f"{path}.path: escapes repository root") from error
    if not artifact.is_file():
        raise GateSContractError(f"{path}.path: artifact does not exist")
    return artifact


def _json_ref(
    value: Any,
    *,
    repository_root: Path,
    expected_schema: str,
    path: str,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    reference = _exact_mapping(value, {"path", "schema_version", "sha256"}, path)
    if reference["schema_version"] != expected_schema:
        raise GateSContractError(f"{path}.schema_version: unsupported")
    _require_hex(reference["sha256"], HEX64, f"{path}.sha256")
    artifact = _artifact_path(repository_root, reference, path)
    payload = artifact.read_bytes()
    if sha256_hex(payload) != reference["sha256"]:
        raise GateSContractError(f"{path}.sha256: does not bind artifact")
    try:
        row = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateSContractError(f"{path}: artifact is not JSON") from error
    if canonical_json_bytes(row) != payload:
        raise GateSContractError(f"{path}: artifact is not canonical JSON")
    if not isinstance(row, dict) or row.get("schema_version") != expected_schema:
        raise GateSContractError(f"{path}: artifact schema does not match reference")
    return reference, row, payload


def _jsonl_ref(
    value: Any,
    *,
    repository_root: Path,
    expected_schema: str,
    path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    reference = _exact_mapping(
        value, {"path", "schema_version", "row_count", "sha256"}, path
    )
    if reference["schema_version"] != expected_schema:
        raise GateSContractError(f"{path}.schema_version: unsupported")
    row_count = reference["row_count"]
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise GateSContractError(f"{path}.row_count: must be non-negative integer")
    _require_hex(reference["sha256"], HEX64, f"{path}.sha256")
    artifact = _artifact_path(repository_root, reference, path)
    payload = artifact.read_bytes()
    if sha256_hex(payload) != reference["sha256"]:
        raise GateSContractError(f"{path}.sha256: does not bind artifact")
    try:
        rows = _load_jsonl_text(payload.decode("utf-8"), str(artifact))
    except UnicodeDecodeError as error:
        raise GateSContractError(f"{path}: artifact is not UTF-8") from error
    if len(rows) != row_count:
        raise GateSContractError(f"{path}.row_count: does not bind artifact")
    if canonical_jsonl_bytes(rows) != payload:
        raise GateSContractError(f"{path}: artifact is not canonical JSONL")
    if any(row.get("schema_version") != expected_schema for row in rows):
        raise GateSContractError(f"{path}: row schema does not match reference")
    return reference, rows, payload


def _source_ref(repository_root: Path, source_path: Path) -> dict[str, str]:
    root = repository_root.resolve()
    resolved = source_path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise GateSContractError("checker source is outside repository root") from error
    return {"path": relative, "sha256": sha256_hex(resolved.read_bytes())}


def _validate_source_ref(
    value: Any, *, repository_root: Path, expected_path: Path, path: str
) -> dict[str, str]:
    reference = _exact_mapping(value, {"path", "sha256"}, path)
    expected = _source_ref(repository_root, expected_path)
    if reference != expected:
        raise GateSContractError(f"{path}: does not bind pinned checker source")
    return reference


def freeze_request_stream(
    board_stream_paths: Sequence[Path],
    output_path: Path,
    *,
    expected_row_count: int,
) -> list[dict[str, Any]]:
    """Freeze every target-free board in input order without checker calls."""

    if not board_stream_paths:
        raise GateSContractError("at least one board stream is required")
    requests: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_boards: set[str] = set()
    seen_reflection_orbits: set[str] = set()
    for stream_path in board_stream_paths:
        stream_rows = load_jsonl(stream_path)
        for expected_ordinal, board_row in enumerate(stream_rows):
            if board_row.get("ordinal") != expected_ordinal:
                raise GateSContractError(
                    f"{stream_path}: ordinals must be contiguous within each shard"
                )
            request = project_request(board_row)
            reflection_orbit = board_row["position"]["symmetry_sha256"]
            if request["board_id"] in seen_ids or request["board_fen"] in seen_boards:
                raise GateSContractError("Gate S inputs must be unique by board id and board field")
            if reflection_orbit in seen_reflection_orbits:
                raise GateSContractError(
                    "Gate S inputs must be unique by file-reflection orbit"
                )
            seen_ids.add(request["board_id"])
            seen_boards.add(request["board_fen"])
            seen_reflection_orbits.add(reflection_orbit)
            requests.append(request)
    if len(requests) != expected_row_count:
        raise GateSContractError(
            f"Gate S requires exactly {expected_row_count} rows, got {len(requests)}"
        )
    _write_bytes(output_path, canonical_jsonl_bytes(requests))
    return requests


def _git_output(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if result.returncode:
        raise GateSContractError(
            f"git inspection failed for {repository}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def verify_clean_checkout(repository: Path, expected_commit: str, name: str) -> None:
    _require_hex(expected_commit, HEX40, f"{name}.expected_commit")
    if _git_output(repository, "rev-parse", "HEAD") != expected_commit:
        raise GateSContractError(f"{name}: checkout is not the pinned commit")
    if _git_output(repository, "status", "--porcelain", "--untracked-files=all"):
        raise GateSContractError(f"{name}: checkout is dirty")


def _git_commit_exists(repository: Path, commit: str, path: str) -> None:
    _require_hex(commit, HEX40, path)
    result = subprocess.run(
        ("git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise GateSContractError(f"{path}: commit is unavailable")


def _require_git_ancestor(repository: Path, ancestor: str, descendant: str) -> None:
    _git_commit_exists(repository, ancestor, "implementation_commit")
    _git_commit_exists(repository, descendant, "supply_pre_result.commit")
    result = subprocess.run(
        ("git", "-C", str(repository), "merge-base", "--is-ancestor", ancestor, descendant),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise GateSContractError("supply_pre_result.commit: I is not its ancestor")


def _require_direct_child(repository: Path, child: str, parent: str) -> None:
    _git_commit_exists(repository, child, "supply_pre_result.commit")
    lineage = _git_output(repository, "rev-list", "--parents", "-n", "1", child).split()
    if lineage != [child, parent]:
        raise GateSContractError(
            "supply_pre_result.commit: P_s must be a direct child of I"
        )


def _commit_diff_entries(
    repository: Path, parent: str, child: str
) -> list[tuple[str, str]]:
    output = _git_output(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "--no-renames",
        "-r",
        parent,
        child,
    )
    entries: list[tuple[str, str]] = []
    for line in output.splitlines():
        try:
            status, relative = line.split("\t", 1)
        except ValueError as error:
            raise GateSContractError("commit diff inventory is malformed") from error
        if status != "A":
            raise GateSContractError(
                f"commit diff inventory must contain additions only: {status} {relative}"
            )
        entries.append((status, relative))
    return entries


def _require_exact_commit_diff(
    repository: Path,
    parent: str,
    child: str,
    expected_paths: Iterable[str],
    label: str,
) -> None:
    observed = sorted(_commit_diff_entries(repository, parent, child))
    expected = sorted(("A", relative) for relative in expected_paths)
    if observed != expected:
        observed_paths = [relative for _, relative in observed]
        expected_path_set = {relative for _, relative in expected}
        observed_path_set = set(observed_paths)
        missing = sorted(expected_path_set - observed_path_set)
        extra = sorted(observed_path_set - expected_path_set)
        raise GateSContractError(
            f"{label}: exact commit diff inventory drift; "
            f"missing={missing}, extra={extra}"
        )


def _require_validator_dependencies_at_i(
    repository: Path, implementation_commit: str
) -> None:
    root = repository.resolve()
    for relative in EVIDENCE_VALIDATOR_DEPENDENCIES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise GateSContractError(
                f"E_s validator dependency is unavailable: {relative}"
            )
        _require_git_artifact(
            root,
            implementation_commit,
            relative,
            path.read_bytes(),
            f"E_s validator dependency {relative}",
        )


def _require_supply_pre_result_boundary(
    repository: Path,
    implementation_commit: str,
    supply_pre_result_commit: str,
    input_root: Path,
) -> None:
    root = repository.resolve()
    _require_direct_child(root, supply_pre_result_commit, implementation_commit)
    frozen_paths = [
        line
        for line in _git_output(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            supply_pre_result_commit,
            SUPPLY_INPUT_ROOT,
        ).splitlines()
        if line
    ]
    if not frozen_paths:
        raise GateSContractError("P_s contains no frozen structural-supply inputs")
    _require_exact_commit_diff(
        root,
        implementation_commit,
        supply_pre_result_commit,
        (*frozen_paths, SUPPLY_FREEZE_DOCUMENT),
        "supply_pre_result.commit",
    )
    _require_supply_tree_frozen(root, supply_pre_result_commit, input_root)
    _require_validator_dependencies_at_i(root, implementation_commit)


def _require_git_artifact(
    repository: Path, commit: str, relative_path: str, payload: bytes, path: str
) -> None:
    relative = _relative_artifact_path(relative_path, f"{path}.path")
    result = subprocess.run(
        ("git", "-C", str(repository), "show", f"{commit}:{relative}"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode or result.stdout != payload:
        raise GateSContractError(f"{path}: bytes are not frozen at the declared commit")


def _require_supply_tree_frozen(
    repository: Path, commit: str, input_root: Path
) -> None:
    root = repository.resolve()
    supply_root = input_root.resolve()
    relative_root = supply_root.relative_to(root).as_posix()
    local_paths = sorted(
        path.relative_to(root).as_posix()
        for path in supply_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    result = subprocess.run(
        ("git", "-C", str(root), "ls-tree", "-r", "--name-only", commit, relative_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    frozen_paths = sorted(line for line in result.stdout.splitlines() if line)
    if result.returncode or frozen_paths != local_paths:
        raise GateSContractError("supply_pre_result.commit: frozen input inventory drift")
    for relative in local_paths:
        _require_git_artifact(
            root,
            commit,
            relative,
            (root / relative).read_bytes(),
            "supply_pre_result.commit",
        )


def _require_evidence_commit_boundary(
    repository: Path,
    supply_pre_result_commit: str,
    artifacts: dict[str, bytes],
) -> str | None:
    """Validate E_s once evidence has been committed; permit only P_s precommit."""

    root = repository.resolve()
    head = _git_output(root, "rev-parse", "HEAD")
    if head == supply_pre_result_commit:
        return None
    _require_git_ancestor(root, supply_pre_result_commit, head)
    history = _git_output(
        root,
        "rev-list",
        "--ancestry-path",
        "--parents",
        f"{supply_pre_result_commit}..{head}",
    )
    candidates = []
    for line in history.splitlines():
        fields = line.split()
        if fields[1:] == [supply_pre_result_commit]:
            candidates.append(fields[0])
    if len(candidates) != 1:
        raise GateSContractError(
            "evidence.commit: expected exactly one direct E_s child of P_s on HEAD ancestry"
        )
    evidence_commit = candidates[0]
    _require_exact_commit_diff(
        root,
        supply_pre_result_commit,
        evidence_commit,
        EVIDENCE_COMMIT_PATHS,
        "evidence.commit",
    )
    for relative, payload in artifacts.items():
        _require_git_artifact(
            root,
            evidence_commit,
            relative,
            payload,
            f"evidence.commit {relative}",
        )
    return evidence_commit


def _supply_module(repository_root: Path) -> Any:
    module_path = repository_root / "python/partizan/wave69r_supply.py"
    specification = importlib.util.spec_from_file_location(
        "partizan_wave69r_supply_for_gate_s", module_path
    )
    if specification is None or specification.loader is None:
        raise GateSContractError("Wave 69-R supply-suite validator is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _validate_supply_suite_reference(
    *,
    repository_root: Path,
    manifest_reference: Any,
    expected_repositories: dict[str, str],
) -> tuple[dict[str, Any], bytes]:
    reference, suite, payload = _json_ref(
        manifest_reference,
        repository_root=repository_root,
        expected_schema=SUPPLY_SUITE_SCHEMA,
        path="supply_pre_result.manifest",
    )
    expected_path = "data/discovery/wave_69r/structural_supply/inputs/suite-manifest.json"
    if reference["path"] != expected_path:
        raise GateSContractError("supply_pre_result.manifest.path: not the frozen path")
    supply = _supply_module(repository_root)
    try:
        validated = supply.validate_supply_suite(
            input_root=(repository_root / reference["path"]).parent,
            expected_commits=expected_repositories,
            repository_root=repository_root,
        )
    except Exception as error:
        raise GateSContractError(f"supply_pre_result.manifest: {error}") from error
    if validated != suite:
        raise GateSContractError("supply_pre_result.manifest: validator payload drift")
    return suite, payload


def _certificate_inventory_from_suite(
    *, repository_root: Path, suite: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    shards = suite.get("shards")
    if not isinstance(shards, list):
        raise GateSContractError("supply suite shards: must be an array")
    references: list[dict[str, Any]] = []
    payloads: list[bytes] = []
    board_ids: list[str] = []
    for index, shard in enumerate(shards):
        entry = _exact_mapping(
            shard,
            {"shard_id", "shard_index", "manifest_ref"},
            f"supply suite shards[{index}]",
        )
        if entry["shard_index"] != index:
            raise GateSContractError("supply suite shard order drift")
        _, shard_manifest, _ = _json_ref(
            entry["manifest_ref"],
            repository_root=repository_root,
            expected_schema=SUPPLY_SHARD_MANIFEST_SCHEMA,
            path=f"supply suite shards[{index}].manifest_ref",
        )
        certificate_reference = shard_manifest.get("construction_certificate_ref")
        reference, certificates, payload = _jsonl_ref(
            certificate_reference,
            repository_root=repository_root,
            expected_schema=SUPPLY_CERTIFICATE_SCHEMA,
            path=f"supply suite shards[{index}].construction_certificate_ref",
        )
        for ordinal, certificate in enumerate(certificates):
            row = _exact_mapping(
                certificate,
                {
                    "schema_version",
                    "certificate_id",
                    "board_id",
                    "ordinal",
                    "catalog_id",
                    "construction_contract",
                    "stratum",
                    "left",
                    "right",
                    "runtime_oracle_used",
                },
                f"construction certificate[{index}][{ordinal}]",
            )
            if row["ordinal"] != ordinal:
                raise GateSContractError("construction certificate order/binding drift")
            _require_hex(
                row["board_id"],
                TYPED_BOARD_ID,
                f"construction certificate[{index}][{ordinal}].board_id",
            )
            board_ids.append(row["board_id"])
        references.append(reference)
        payloads.append(payload)
    inventory = {
        "schema_version": SUPPLY_CERTIFICATE_SCHEMA,
        "shard_count": len(references),
        "row_count": len(board_ids),
        "references_sha256": sha256_hex(canonical_json_bytes(references)),
        "canonical_jsonl_sha256": sha256_hex(b"".join(payloads)),
    }
    return inventory, board_ids


def validate_result(value: Any, expected_board_id: str | None = None) -> dict[str, Any]:
    row = _exact_mapping(value, _RESULT_KEYS, "result")
    if row["schema_version"] != RESULT_SCHEMA:
        raise GateSContractError("result.schema_version: unsupported")
    _require_hex(row["board_id"], TYPED_BOARD_ID, "result.board_id")
    if expected_board_id is not None and row["board_id"] != expected_board_id:
        raise GateSContractError("result.board_id: input order/binding mismatch")
    checker = _exact_mapping(
        row["checker"],
        {"name", "version", "bitmesh_crate_version", "bitmesh_source_commit", "proof_api"},
        "result.checker",
    )
    if checker != {
        "name": CHECKER_NAME,
        "version": CHECKER_VERSION,
        "bitmesh_crate_version": BITMESH_CRATE_VERSION,
        "bitmesh_source_commit": BITMESH_COMMIT,
        "proof_api": PROOF_API,
    }:
        raise GateSContractError("result.checker: does not equal pinned provenance")
    predicates = _exact_mapping(row["predicates"], _PREDICATE_KEYS, "result.predicates")
    if any(state not in _PREDICATE_STATES for state in predicates.values()):
        raise GateSContractError("result.predicates: invalid tri-state value")
    failure_code = row["failure_code"]
    if failure_code is not None and failure_code not in _FAILURE_CODES:
        raise GateSContractError("result.failure_code: unknown mapping")
    if not isinstance(row["internal_error"], bool):
        raise GateSContractError("result.internal_error: must be boolean")

    certification = row["certification"]
    if certification is not None:
        cert = _exact_mapping(
            certification,
            {"proof_kind", "decomposition_sha256", "component_count", "barrier_squares"},
            "result.certification",
        )
        if cert["proof_kind"] != PROOF_API:
            raise GateSContractError("result.certification.proof_kind: unsupported")
        _require_hex(cert["decomposition_sha256"], HEX64, "certification.decomposition_sha256")
        if not isinstance(cert["component_count"], int) or isinstance(cert["component_count"], bool):
            raise GateSContractError("certification.component_count: must be integer")
        squares = cert["barrier_squares"]
        if not isinstance(squares, list) or not all(
            isinstance(square, str) and re.fullmatch(r"[a-h][1-8]", square)
            for square in squares
        ):
            raise GateSContractError("certification.barrier_squares: invalid")

    outcome = row["outcome"]
    if outcome == "pass":
        if (
            certification is None
            or certification["component_count"] != 2
            or failure_code is not None
            or row["internal_error"]
            or set(predicates.values()) != {"pass"}
        ):
            raise GateSContractError("result.outcome: pass invariants failed")
    elif outcome == "fail":
        if failure_code is None or row["internal_error"]:
            raise GateSContractError("result.outcome: fail invariants failed")
        all_not_evaluated = dict.fromkeys(_PREDICATE_KEYS, "not_evaluated")
        expected_predicates = dict(all_not_evaluated)
        if failure_code == "structure.component_count_not_two":
            expected_predicates = {
                "frozen_barrier": "pass",
                "non_capturable_barrier": "pass",
                "strict_exactly_two_components": "fail",
                "no_cross_component_entry": "pass",
            }
            if certification is None or certification["component_count"] == 2:
                raise GateSContractError(
                    "component-count failure requires a non-two Bitmesh certification"
                )
        else:
            if certification is not None:
                raise GateSContractError(
                    "only a component-count failure may retain a certification"
                )
            if failure_code.startswith("bitmesh.invalid_certificate.") or failure_code == (
                "bitmesh.requires_strict_decomposition"
            ):
                expected_predicates["strict_exactly_two_components"] = "fail"
            elif failure_code in {
                "bitmesh.barrier_square_is_empty",
                "bitmesh.barrier_square_is_not_pawn",
                "bitmesh.barrier_pawn_not_frozen",
            }:
                expected_predicates["frozen_barrier"] = "fail"
            elif failure_code == "bitmesh.barrier_pawn_can_capture":
                expected_predicates["non_capturable_barrier"] = "fail"
            elif failure_code == "bitmesh.barrier_piece_can_be_captured":
                expected_predicates["frozen_barrier"] = "pass"
                expected_predicates["non_capturable_barrier"] = "fail"
            elif failure_code in {
                "bitmesh.active_piece_outside_certified_component",
                "bitmesh.piece_can_enter_other_component",
                "bitmesh.piece_can_enter_uncertified_free_square",
            }:
                expected_predicates["frozen_barrier"] = "pass"
                expected_predicates["no_cross_component_entry"] = "fail"
            elif failure_code != "input.invalid_board_fen":
                raise GateSContractError("result.failure_code: invalid fail outcome mapping")
        if predicates != expected_predicates:
            raise GateSContractError("result.predicates: inconsistent with first failure")
    elif outcome == "error":
        if (
            not row["internal_error"]
            or failure_code != "checker.internal_error"
            or certification is not None
            or set(predicates.values()) != {"not_evaluated"}
        ):
            raise GateSContractError("result.outcome: error invariants failed")
    else:
        raise GateSContractError("result.outcome: invalid")
    return row


def evaluate_request_stream(
    request_path: Path,
    result_path: Path,
    *,
    bitmesh_dir: Path,
    expected_partizan_commit: str,
    expected_row_count: int,
) -> list[dict[str, Any]]:
    """Run the isolated checker once per frozen row and retain every result."""

    requests = [validate_request(row) for row in load_jsonl(request_path)]
    if len(requests) != expected_row_count:
        raise GateSContractError(
            f"frozen request count differs: expected {expected_row_count}, got {len(requests)}"
        )
    verify_clean_checkout(ROOT, expected_partizan_commit, "partizan")
    verify_clean_checkout(bitmesh_dir.resolve(), BITMESH_COMMIT, "bitmesh")
    patch_config = (
        'patch."crates-io".bitmesh.path='
        + json.dumps(str(bitmesh_dir.resolve()))
    )
    with tempfile.TemporaryDirectory(prefix="partizan-gate-s-cargo-") as target_dir:
        environment = dict(os.environ)
        environment["CARGO_TARGET_DIR"] = target_dir
        result = subprocess.run(
            (
                "cargo",
                "--config",
                patch_config,
                "run",
                "--manifest-path",
                str(CHECKER_MANIFEST),
                "--locked",
                "--offline",
                "--quiet",
            ),
            cwd=ROOT,
            env=environment,
            input=canonical_jsonl_bytes(requests),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode:
        raise GateSContractError(
            "structure-only checker failed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        output_text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GateSContractError("checker output is not UTF-8") from error
    raw_results = _load_jsonl_text(output_text, "checker stdout")
    if len(raw_results) != len(requests):
        raise GateSContractError("checker must emit exactly one result per input")
    results = [
        validate_result(row, request["board_id"])
        for row, request in zip(raw_results, requests)
    ]
    _write_bytes(result_path, canonical_jsonl_bytes(results))
    return results


def summarize_results(
    request_rows: Sequence[dict[str, Any]],
    result_rows: Sequence[dict[str, Any]],
    *,
    expected_row_count: int = GATE_S_ROW_COUNT,
) -> dict[str, Any]:
    requests = [validate_request(row) for row in request_rows]
    if len(requests) != len(result_rows):
        raise GateSContractError("request/result row counts differ")
    results = [
        validate_result(result, request["board_id"])
        for request, result in zip(requests, result_rows)
    ]
    predicate_counts = {
        predicate: dict(Counter(row["predicates"][predicate] for row in results))
        for predicate in sorted(_PREDICATE_KEYS)
    }
    return {
        "row_count": len(results),
        "outcomes": dict(Counter(row["outcome"] for row in results)),
        "predicate_counts": predicate_counts,
        "internal_errors": sum(row["internal_error"] for row in results),
        "go": len(results) == expected_row_count
        and all(row["outcome"] == "pass" for row in results)
        and all(not row["internal_error"] for row in results),
    }


def evidence_id_for(value: dict[str, Any]) -> str:
    identity = dict(value)
    identity.pop("evidence_id", None)
    return "evidence-sha256:" + sha256_hex(canonical_json_bytes(identity))


def _artifact_reference(
    *, path: str, schema_version: str, payload: bytes, row_count: int | None = None
) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "path": _relative_artifact_path(path, "artifact.path"),
        "schema_version": schema_version,
        "sha256": sha256_hex(payload),
    }
    if row_count is not None:
        reference["row_count"] = row_count
    return reference


def _validate_source_repositories(value: Any, implementation_commit: str) -> dict[str, str]:
    repositories = _exact_mapping(
        value, {"partizan", "astralbase", "bitmesh", "thermograph"}, "source_repositories"
    )
    expected = {
        "partizan": implementation_commit,
        "astralbase": ASTRALBASE_COMMIT,
        "bitmesh": BITMESH_COMMIT,
        "thermograph": THERMOGRAPH_COMMIT,
    }
    for name, commit in repositories.items():
        _require_hex(commit, HEX40, f"source_repositories.{name}")
    if repositories != expected:
        raise GateSContractError("source_repositories: do not equal Wave 69-R pins")
    return repositories


def _checker_binding(repository_root: Path) -> dict[str, Any]:
    return {
        "name": CHECKER_NAME,
        "version": CHECKER_VERSION,
        "manifest": _source_ref(
            repository_root, repository_root / CHECKER_MANIFEST.relative_to(ROOT)
        ),
        "lock": _source_ref(repository_root, repository_root / CHECKER_LOCK.relative_to(ROOT)),
        "source": _source_ref(repository_root, repository_root / CHECKER_SOURCE.relative_to(ROOT)),
        "wrapper": _source_ref(
            repository_root, repository_root / CHECKER_WRAPPER.relative_to(ROOT)
        ),
        "bitmesh_crate_version": BITMESH_CRATE_VERSION,
        "bitmesh_source_commit": BITMESH_COMMIT,
        "proof_api": PROOF_API,
    }


def _fixed_counts(counter: Counter[str], keys: Iterable[str]) -> dict[str, int]:
    return {key: counter.get(key, 0) for key in sorted(keys)}


def _compose_evidence_manifest(
    *,
    repository_root: Path,
    implementation_commit: str,
    supply_pre_result_commit: str,
    supply_manifest_reference: dict[str, Any],
    checker_request_reference: dict[str, Any],
    requests: Sequence[dict[str, Any]],
    primary_reference: dict[str, Any],
    primary_results: Sequence[dict[str, Any]],
    primary_payload: bytes,
    replay_reference: dict[str, Any],
    replay_results: Sequence[dict[str, Any]],
    replay_payload: bytes,
    construction_certificate_inventory: dict[str, Any],
    construction_certificate_board_ids: Sequence[str],
    source_repositories: dict[str, str],
) -> dict[str, Any]:
    _require_hex(implementation_commit, HEX40, "implementation_commit")
    _require_hex(supply_pre_result_commit, HEX40, "supply_pre_result.commit")
    repositories = _validate_source_repositories(
        source_repositories, implementation_commit
    )
    validated_requests = [validate_request(row) for row in requests]
    if len(primary_results) != len(validated_requests) or len(replay_results) != len(
        validated_requests
    ):
        raise GateSContractError("evidence ledgers must retain one row per request")
    primary = [
        validate_result(result, request["board_id"])
        for result, request in zip(primary_results, validated_requests)
    ]
    replay = [
        validate_result(result, request["board_id"])
        for result, request in zip(replay_results, validated_requests)
    ]
    if canonical_jsonl_bytes(primary) != primary_payload:
        raise GateSContractError("primary result ledger is not canonical")
    if canonical_jsonl_bytes(replay) != replay_payload:
        raise GateSContractError("replay result ledger is not canonical")
    certificate_inventory = _exact_mapping(
        construction_certificate_inventory,
        {
            "schema_version",
            "shard_count",
            "row_count",
            "references_sha256",
            "canonical_jsonl_sha256",
        },
        "construction_certificate_inventory",
    )
    if certificate_inventory["schema_version"] != SUPPLY_CERTIFICATE_SCHEMA:
        raise GateSContractError("construction certificate schema drift")
    for key in ("references_sha256", "canonical_jsonl_sha256"):
        _require_hex(certificate_inventory[key], HEX64, f"certificate_inventory.{key}")
    if list(construction_certificate_board_ids) != [
        request["board_id"] for request in validated_requests
    ]:
        raise GateSContractError("construction certificates do not bind request order")
    construction_certificate_count = certificate_inventory["row_count"]

    outcome_counts = _fixed_counts(
        Counter(row["outcome"] for row in primary), {"pass", "fail", "error"}
    )
    predicate_counts = {
        predicate: _fixed_counts(
            Counter(row["predicates"][predicate] for row in primary),
            _PREDICATE_STATES,
        )
        for predicate in sorted(_PREDICATE_KEYS)
    }
    failure_counts = Counter(
        row["failure_code"] for row in primary if row["failure_code"] is not None
    )
    byte_identical = primary_payload == replay_payload
    certificate_disagreements = sum(
        first["outcome"] != "pass" or second["outcome"] != "pass"
        for first, second in zip(primary, replay)
    )
    row_count = len(primary)
    complete = (
        len(validated_requests)
        == len(primary)
        == len(replay)
        == GATE_S_ROW_COUNT
    )
    go = (
        complete
        and construction_certificate_count == GATE_S_ROW_COUNT
        and byte_identical
        and outcome_counts == {"error": 0, "fail": 0, "pass": GATE_S_ROW_COUNT}
        and all(
            counts == {"fail": 0, "not_evaluated": 0, "pass": GATE_S_ROW_COUNT}
            for counts in predicate_counts.values()
        )
        and not failure_counts
        and not any(row["internal_error"] for row in primary)
        and certificate_disagreements == 0
    )
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "evidence_id": "evidence-sha256:" + "0" * 64,
        "audit_contract": "partizan.wave69r_structural_supply_audit.v0.1",
        "decision": "GO" if go else "NO-GO",
        "implementation_commit": implementation_commit,
        "supply_pre_result": {
            "commit": supply_pre_result_commit,
            "manifest": supply_manifest_reference,
            "checker_request_ref": checker_request_reference,
            "construction_certificate_inventory": certificate_inventory,
        },
        "source_repositories": repositories,
        "checker": _checker_binding(repository_root),
        "executions": {
            "mode": "separate_checker_processes_v1",
            "run_count": 2,
            "primary_ledger": primary_reference,
            "replay_ledger": replay_reference,
            "byte_identical": byte_identical,
        },
        "audit": {
            "expected_row_count": GATE_S_ROW_COUNT,
            "observed_row_count": row_count,
            "construction_certificate_count": construction_certificate_count,
            "outcome_counts": outcome_counts,
            "predicate_counts": predicate_counts,
            "failure_code_counts": [
                {"code": code, "count": failure_counts[code]}
                for code in sorted(failure_counts)
            ],
            "internal_error_count": sum(row["internal_error"] for row in primary),
            "certificate_disagreement_count": certificate_disagreements,
            "complete_ledger": complete,
            "request_result_binding": True,
            "forbidden_field_scan": True,
        },
    }
    evidence["evidence_id"] = evidence_id_for(evidence)
    return evidence


def build_evidence_manifest(
    *,
    repository_root: Path,
    implementation_commit: str,
    supply_pre_result_commit: str,
    supply_manifest_path: str,
    primary_ledger_path: str,
    replay_ledger_path: str,
    require_git_binding: bool = True,
) -> dict[str, Any]:
    """Build E_s from already-written P_s inputs and two complete ledgers."""

    root = repository_root.resolve()
    supply_manifest_path = _relative_artifact_path(
        supply_manifest_path, "supply_pre_result.manifest.path"
    )
    supply_payload = (root / supply_manifest_path).read_bytes()
    supply_reference = _artifact_reference(
        path=supply_manifest_path,
        schema_version=SUPPLY_SUITE_SCHEMA,
        payload=supply_payload,
    )
    try:
        supply_row = json.loads(supply_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateSContractError("supply manifest is not JSON") from error
    repositories = _validate_source_repositories(
        supply_row.get("source_repositories"), implementation_commit
    )
    if require_git_binding:
        _require_supply_pre_result_boundary(
            root,
            implementation_commit,
            supply_pre_result_commit,
            (root / supply_manifest_path).parent,
        )
    suite, validated_supply_payload = _validate_supply_suite_reference(
        repository_root=root,
        manifest_reference=supply_reference,
        expected_repositories=repositories,
    )
    if supply_payload != validated_supply_payload:
        raise GateSContractError("supply manifest validation changed its bytes")
    if suite.get("implementation_commit") != implementation_commit:
        raise GateSContractError("supply manifest does not bind implementation I")
    request_reference = suite.get("checker_request_ref")
    _, requests, _ = _jsonl_ref(
        request_reference,
        repository_root=root,
        expected_schema=REQUEST_SCHEMA,
        path="supply_pre_result.checker_request_ref",
    )
    for row in requests:
        validate_request(row)
    certificate_inventory, certificate_board_ids = _certificate_inventory_from_suite(
        repository_root=root, suite=suite
    )

    primary_path = _relative_artifact_path(
        primary_ledger_path, "executions.primary_ledger.path"
    )
    if primary_path != EVIDENCE_PRIMARY_PATH:
        raise GateSContractError("executions.primary_ledger.path: not the frozen E_s path")
    primary_payload = (root / primary_path).read_bytes()
    primary_reference = _artifact_reference(
        path=primary_path,
        schema_version=RESULT_SCHEMA,
        payload=primary_payload,
        row_count=len(requests),
    )
    _, primary_rows, _ = _jsonl_ref(
        primary_reference,
        repository_root=root,
        expected_schema=RESULT_SCHEMA,
        path="executions.primary_ledger",
    )
    replay_path = _relative_artifact_path(
        replay_ledger_path, "executions.replay_ledger.path"
    )
    if replay_path != EVIDENCE_REPLAY_PATH:
        raise GateSContractError("executions.replay_ledger.path: not the frozen E_s path")
    replay_payload = (root / replay_path).read_bytes()
    replay_reference = _artifact_reference(
        path=replay_path,
        schema_version=RESULT_SCHEMA,
        payload=replay_payload,
        row_count=len(requests),
    )
    _, replay_rows, _ = _jsonl_ref(
        replay_reference,
        repository_root=root,
        expected_schema=RESULT_SCHEMA,
        path="executions.replay_ledger",
    )
    return _compose_evidence_manifest(
        repository_root=root,
        implementation_commit=implementation_commit,
        supply_pre_result_commit=supply_pre_result_commit,
        supply_manifest_reference=supply_reference,
        checker_request_reference=request_reference,
        requests=requests,
        primary_reference=primary_reference,
        primary_results=primary_rows,
        primary_payload=primary_payload,
        replay_reference=replay_reference,
        replay_results=replay_rows,
        replay_payload=replay_payload,
        construction_certificate_inventory=certificate_inventory,
        construction_certificate_board_ids=certificate_board_ids,
        source_repositories=repositories,
    )


def validate_evidence_manifest(
    value: Any,
    *,
    repository_root: Path = ROOT,
    require_git_binding: bool = True,
) -> dict[str, Any]:
    """Recompute E_s from bound bytes without invoking the checker."""

    row = _exact_mapping(
        value,
        {
            "schema_version",
            "evidence_id",
            "audit_contract",
            "decision",
            "implementation_commit",
            "supply_pre_result",
            "source_repositories",
            "checker",
            "executions",
            "audit",
        },
        "evidence",
    )
    if row["schema_version"] != EVIDENCE_SCHEMA:
        raise GateSContractError("evidence.schema_version: unsupported")
    _require_hex(row["evidence_id"], TYPED_EVIDENCE_ID, "evidence.evidence_id")
    if row["audit_contract"] != "partizan.wave69r_structural_supply_audit.v0.1":
        raise GateSContractError("evidence.audit_contract: unsupported")
    if row["decision"] not in {"GO", "NO-GO"}:
        raise GateSContractError("evidence.decision: invalid")
    implementation_commit = _require_hex(
        row["implementation_commit"], HEX40, "evidence.implementation_commit"
    )
    repositories = _validate_source_repositories(
        row["source_repositories"], implementation_commit
    )
    supply = _exact_mapping(
        row["supply_pre_result"],
        {
            "commit",
            "manifest",
            "checker_request_ref",
            "construction_certificate_inventory",
        },
        "evidence.supply_pre_result",
    )
    supply_commit = _require_hex(
        supply["commit"], HEX40, "evidence.supply_pre_result.commit"
    )
    root = repository_root.resolve()
    if require_git_binding:
        manifest = _exact_mapping(
            supply["manifest"],
            {"path", "schema_version", "sha256"},
            "evidence.supply_pre_result.manifest",
        )
        manifest_path = _relative_artifact_path(
            manifest["path"], "evidence.supply_pre_result.manifest.path"
        )
        _require_supply_pre_result_boundary(
            root,
            implementation_commit,
            supply_commit,
            (root / manifest_path).parent,
        )
    suite, suite_payload = _validate_supply_suite_reference(
        repository_root=root,
        manifest_reference=supply["manifest"],
        expected_repositories=repositories,
    )
    if suite.get("implementation_commit") != implementation_commit:
        raise GateSContractError("evidence: P_s does not bind implementation I")
    if supply["checker_request_ref"] != suite.get("checker_request_ref"):
        raise GateSContractError("evidence: checker request is not the P_s projection")
    _, requests, _ = _jsonl_ref(
        supply["checker_request_ref"],
        repository_root=root,
        expected_schema=REQUEST_SCHEMA,
        path="evidence.supply_pre_result.checker_request_ref",
    )
    for request in requests:
        validate_request(request)
    certificate_inventory, certificate_board_ids = _certificate_inventory_from_suite(
        repository_root=root, suite=suite
    )
    if supply["construction_certificate_inventory"] != certificate_inventory:
        raise GateSContractError("evidence: construction certificate inventory drift")
    if require_git_binding:
        _require_git_artifact(
            root,
            supply_commit,
            supply["manifest"]["path"],
            suite_payload,
            "evidence.supply_pre_result.manifest",
        )
        _require_supply_tree_frozen(
            root,
            supply_commit,
            (root / supply["manifest"]["path"]).parent,
        )

    checker = _exact_mapping(
        row["checker"],
        {
            "name",
            "version",
            "manifest",
            "lock",
            "source",
            "wrapper",
            "bitmesh_crate_version",
            "bitmesh_source_commit",
            "proof_api",
        },
        "evidence.checker",
    )
    expected_checker = _checker_binding(root)
    if checker != expected_checker:
        raise GateSContractError("evidence.checker: source/provenance binding drift")
    for key, expected_path in (
        ("manifest", root / CHECKER_MANIFEST.relative_to(ROOT)),
        ("lock", root / CHECKER_LOCK.relative_to(ROOT)),
        ("source", root / CHECKER_SOURCE.relative_to(ROOT)),
        ("wrapper", root / CHECKER_WRAPPER.relative_to(ROOT)),
    ):
        _validate_source_ref(
            checker[key],
            repository_root=root,
            expected_path=expected_path,
            path=f"evidence.checker.{key}",
        )
        if require_git_binding:
            _require_git_artifact(
                root,
                implementation_commit,
                checker[key]["path"],
                expected_path.read_bytes(),
                f"evidence.checker.{key}",
            )

    executions = _exact_mapping(
        row["executions"],
        {"mode", "run_count", "primary_ledger", "replay_ledger", "byte_identical"},
        "evidence.executions",
    )
    primary_binding = _exact_mapping(
        executions["primary_ledger"],
        {"path", "schema_version", "row_count", "sha256"},
        "evidence.executions.primary_ledger",
    )
    replay_binding = _exact_mapping(
        executions["replay_ledger"],
        {"path", "schema_version", "row_count", "sha256"},
        "evidence.executions.replay_ledger",
    )
    if (
        primary_binding["path"] != EVIDENCE_PRIMARY_PATH
        or replay_binding["path"] != EVIDENCE_REPLAY_PATH
    ):
        raise GateSContractError("evidence.executions: ledger paths are not frozen")
    _, primary, primary_payload = _jsonl_ref(
        executions["primary_ledger"],
        repository_root=root,
        expected_schema=RESULT_SCHEMA,
        path="evidence.executions.primary_ledger",
    )
    _, replay, replay_payload = _jsonl_ref(
        executions["replay_ledger"],
        repository_root=root,
        expected_schema=RESULT_SCHEMA,
        path="evidence.executions.replay_ledger",
    )
    expected = _compose_evidence_manifest(
        repository_root=root,
        implementation_commit=implementation_commit,
        supply_pre_result_commit=supply_commit,
        supply_manifest_reference=supply["manifest"],
        checker_request_reference=supply["checker_request_ref"],
        requests=requests,
        primary_reference=executions["primary_ledger"],
        primary_results=primary,
        primary_payload=primary_payload,
        replay_reference=executions["replay_ledger"],
        replay_results=replay,
        replay_payload=replay_payload,
        construction_certificate_inventory=certificate_inventory,
        construction_certificate_board_ids=certificate_board_ids,
        source_repositories=repositories,
    )
    if row != expected:
        raise GateSContractError("evidence: does not equal recomputed canonical audit")
    if require_git_binding:
        _require_evidence_commit_boundary(
            root,
            supply_commit,
            {
                EVIDENCE_PRIMARY_PATH: primary_payload,
                EVIDENCE_REPLAY_PATH: replay_payload,
                EVIDENCE_MANIFEST_PATH: canonical_json_bytes(row),
            },
        )
    return row


def check_evidence_file(
    path: Path, *, repository_root: Path = ROOT, require_git_binding: bool = True
) -> dict[str, Any]:
    if require_git_binding:
        try:
            relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
        except ValueError as error:
            raise GateSContractError("evidence file is outside the repository") from error
        if relative != EVIDENCE_MANIFEST_PATH:
            raise GateSContractError("evidence file path is not the frozen E_s path")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateSContractError("evidence file is not JSON") from error
    if canonical_json_bytes(value) != payload:
        raise GateSContractError("evidence file is not canonical JSON")
    return validate_evidence_manifest(
        value,
        repository_root=repository_root,
        require_git_binding=require_git_binding,
    )


def execute_evidence(
    *,
    artifact_root: Path,
    implementation_commit: str,
    supply_pre_result_commit: str,
    supply_manifest_path: str,
    primary_ledger_path: str,
    replay_ledger_path: str,
    evidence_path: str,
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
) -> dict[str, Any]:
    """Run two independent checker processes, then write canonical E_s bytes."""

    artifacts = artifact_root.resolve()
    if artifacts == ROOT.resolve():
        raise GateSContractError("I implementation root and P_s artifact root must differ")
    verify_clean_checkout(ROOT, implementation_commit, "partizan I")
    verify_clean_checkout(artifacts, supply_pre_result_commit, "partizan P_s")
    _require_supply_pre_result_boundary(
        artifacts,
        implementation_commit,
        supply_pre_result_commit,
        artifacts / SUPPLY_INPUT_ROOT,
    )
    for implementation_path in (
        CHECKER_MANIFEST,
        CHECKER_LOCK,
        CHECKER_SOURCE,
        CHECKER_WRAPPER,
    ):
        relative = implementation_path.relative_to(ROOT).as_posix()
        _require_git_artifact(
            ROOT,
            implementation_commit,
            relative,
            implementation_path.read_bytes(),
            "partizan I checker source",
        )
    verify_clean_checkout(astralbase_dir.resolve(), ASTRALBASE_COMMIT, "astralbase")
    verify_clean_checkout(bitmesh_dir.resolve(), BITMESH_COMMIT, "bitmesh")
    verify_clean_checkout(thermograph_dir.resolve(), THERMOGRAPH_COMMIT, "thermograph")
    output_paths = [
        _relative_artifact_path(primary_ledger_path, "primary_ledger_path"),
        _relative_artifact_path(replay_ledger_path, "replay_ledger_path"),
        _relative_artifact_path(evidence_path, "evidence_path"),
    ]
    if output_paths != [
        EVIDENCE_PRIMARY_PATH,
        EVIDENCE_REPLAY_PATH,
        EVIDENCE_MANIFEST_PATH,
    ]:
        raise GateSContractError("E_s output paths do not equal the frozen inventory")
    if any((artifacts / path).exists() for path in output_paths):
        raise GateSContractError("E_s outputs already exist; replacement is forbidden")

    manifest_path = _relative_artifact_path(
        supply_manifest_path, "supply_manifest_path"
    )
    supply_payload = (artifacts / manifest_path).read_bytes()
    supply_reference = _artifact_reference(
        path=manifest_path,
        schema_version=SUPPLY_SUITE_SCHEMA,
        payload=supply_payload,
    )
    expected_repositories = {
        "partizan": implementation_commit,
        "astralbase": ASTRALBASE_COMMIT,
        "bitmesh": BITMESH_COMMIT,
        "thermograph": THERMOGRAPH_COMMIT,
    }
    suite, _ = _validate_supply_suite_reference(
        repository_root=artifacts,
        manifest_reference=supply_reference,
        expected_repositories=expected_repositories,
    )
    request_reference = suite.get("checker_request_ref")
    if not isinstance(request_reference, dict):
        raise GateSContractError("P_s suite has no checker request reference")
    request_path = _artifact_path(
        artifacts, request_reference, "supply_pre_result.checker_request_ref"
    )

    with tempfile.TemporaryDirectory(prefix="partizan-wave69r-e-s-") as directory:
        temporary = Path(directory)
        primary_temporary = temporary / "primary.jsonl"
        replay_temporary = temporary / "replay.jsonl"
        evaluate_request_stream(
            request_path,
            primary_temporary,
            bitmesh_dir=bitmesh_dir,
            expected_partizan_commit=implementation_commit,
            expected_row_count=GATE_S_ROW_COUNT,
        )
        evaluate_request_stream(
            request_path,
            replay_temporary,
            bitmesh_dir=bitmesh_dir,
            expected_partizan_commit=implementation_commit,
            expected_row_count=GATE_S_ROW_COUNT,
        )
        primary_payload = primary_temporary.read_bytes()
        replay_payload = replay_temporary.read_bytes()

    _write_bytes(artifacts / output_paths[0], primary_payload)
    _write_bytes(artifacts / output_paths[1], replay_payload)
    evidence = build_evidence_manifest(
        repository_root=artifacts,
        implementation_commit=implementation_commit,
        supply_pre_result_commit=supply_pre_result_commit,
        supply_manifest_path=manifest_path,
        primary_ledger_path=output_paths[0],
        replay_ledger_path=output_paths[1],
        require_git_binding=True,
    )
    _write_bytes(artifacts / output_paths[2], canonical_json_bytes(evidence))
    check_evidence_file(artifacts / output_paths[2], repository_root=artifacts)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze = subparsers.add_parser("freeze", help="project board streams to checker requests")
    freeze.add_argument("--board-stream", action="append", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate", help="run only the pinned Bitmesh checker")
    evaluate.add_argument("--suite", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--bitmesh-dir", type=Path, required=True)
    evaluate.add_argument("--expected-partizan-commit", required=True)

    summarize = subparsers.add_parser("summarize", help="recompute a target-free gate summary")
    summarize.add_argument("--suite", type=Path, required=True)
    summarize.add_argument("--results", type=Path, required=True)

    execute_e_s = subparsers.add_parser(
        "execute-evidence", help="run two independent Gate S processes and write E_s"
    )
    execute_e_s.add_argument("--artifact-root", type=Path, required=True)
    execute_e_s.add_argument("--implementation-commit", required=True)
    execute_e_s.add_argument("--supply-pre-result-commit", required=True)
    execute_e_s.add_argument("--supply-manifest", required=True)
    execute_e_s.add_argument("--primary-output", required=True)
    execute_e_s.add_argument("--replay-output", required=True)
    execute_e_s.add_argument("--evidence-output", required=True)
    execute_e_s.add_argument("--astralbase-dir", type=Path, required=True)
    execute_e_s.add_argument("--bitmesh-dir", type=Path, required=True)
    execute_e_s.add_argument("--thermograph-dir", type=Path, required=True)

    check_e_s = subparsers.add_parser(
        "check-evidence", help="revalidate frozen E_s without checker execution"
    )
    check_e_s.add_argument("--evidence", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "freeze":
        rows = freeze_request_stream(
            args.board_stream,
            args.output,
            expected_row_count=GATE_S_ROW_COUNT,
        )
        print(f"wave69r-gate-s-freeze: ok rows={len(rows)} sha256={sha256_hex(args.output.read_bytes())}")
        return 0
    if args.command == "evaluate":
        rows = evaluate_request_stream(
            args.suite,
            args.output,
            bitmesh_dir=args.bitmesh_dir,
            expected_partizan_commit=args.expected_partizan_commit,
            expected_row_count=GATE_S_ROW_COUNT,
        )
        print(f"wave69r-gate-s-evaluate: ok rows={len(rows)} sha256={sha256_hex(args.output.read_bytes())}")
        return 0
    if args.command == "execute-evidence":
        evidence = execute_evidence(
            artifact_root=args.artifact_root,
            implementation_commit=args.implementation_commit,
            supply_pre_result_commit=args.supply_pre_result_commit,
            supply_manifest_path=args.supply_manifest,
            primary_ledger_path=args.primary_output,
            replay_ledger_path=args.replay_output,
            evidence_path=args.evidence_output,
            astralbase_dir=args.astralbase_dir,
            bitmesh_dir=args.bitmesh_dir,
            thermograph_dir=args.thermograph_dir,
        )
        print(
            "wave69r-gate-s-evidence: ok "
            f"decision={evidence['decision']} evidence_id={evidence['evidence_id']}"
        )
        return 0
    if args.command == "check-evidence":
        evidence = check_evidence_file(args.evidence)
        print(
            "wave69r-gate-s-check-evidence: ok "
            f"decision={evidence['decision']} evidence_id={evidence['evidence_id']}"
        )
        return 0
    summary = summarize_results(load_jsonl(args.suite), load_jsonl(args.results))
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
