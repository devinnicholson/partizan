#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATED_ARTIFACT_DIR = ROOT / "artifacts" / "generated"
DEFAULT_SHARD_PATH = GENERATED_ARTIFACT_DIR / "partizan-wave-03.jsonl"
DEFAULT_FRONTIER_SHARD_PATH = GENERATED_ARTIFACT_DIR / "partizan-frontier-wave-06.jsonl"
DEFAULT_FAMILY_FRONTIER_SHARD_PATH = (
    GENERATED_ARTIFACT_DIR / "partizan-family-frontier-wave-07.jsonl"
)
DEFAULT_EXPANDED_FAMILY_FRONTIER_SHARD_PATH = Path(
    GENERATED_ARTIFACT_DIR / "partizan-expanded-family-frontier-wave-12.jsonl"
)
DEFAULT_COMPOSITION_HARD_TARGET_SHARD_PATH = Path(
    GENERATED_ARTIFACT_DIR / "partizan-composition-hard-target-wave-17.jsonl"
)
DEFAULT_MANIFEST_PATH = GENERATED_ARTIFACT_DIR / "partizan-wave-03.manifest.md"
DEFAULT_FRONTIER_MANIFEST_PATH = GENERATED_ARTIFACT_DIR / "partizan-frontier-wave-06.manifest.md"
DEFAULT_FAMILY_FRONTIER_MANIFEST_PATH = (
    GENERATED_ARTIFACT_DIR / "partizan-family-frontier-wave-07.manifest.md"
)
DEFAULT_EXPANDED_FAMILY_FRONTIER_MANIFEST_PATH = (
    GENERATED_ARTIFACT_DIR / "partizan-expanded-family-frontier-wave-12.manifest.md"
)
DEFAULT_COMPOSITION_HARD_TARGET_MANIFEST_PATH = (
    GENERATED_ARTIFACT_DIR / "partizan-composition-hard-target-wave-17.manifest.md"
)
LABEL_SCHEMA_PATH = ROOT / "agents" / "label_schema.py"
SCHEMA_VERSION = "partizan.dataset_label.v0"
ASTRALBASE_SHARD_COMMAND = (
    "cargo",
    "run",
    "--locked",
    "--offline",
    "--quiet",
    "--",
    "--sample-label-shard",
)
ASTRALBASE_FRONTIER_SHARD_BASE_COMMAND = (
    "cargo",
    "run",
    "--locked",
    "--offline",
    "--quiet",
    "--",
    "--frontier-label-shard",
)
ASTRALBASE_FAMILY_FRONTIER_SHARD_BASE_COMMAND = (
    "cargo",
    "run",
    "--locked",
    "--offline",
    "--quiet",
    "--",
    "--family-frontier-label-shard",
)
ASTRALBASE_EXPANDED_FAMILY_FRONTIER_SHARD_BASE_COMMAND = (
    "cargo",
    "run",
    "--locked",
    "--offline",
    "--quiet",
    "--",
    "--expanded-family-frontier-label-shard",
)
ASTRALBASE_COMPOSITION_HARD_TARGET_SHARD_BASE_COMMAND = (
    "cargo",
    "run",
    "--locked",
    "--offline",
    "--quiet",
    "--",
    "--composition-hard-target-shard",
)
DEFAULT_FRONTIER_LIMIT = 1_000
DEFAULT_FAMILY_FRONTIER_LIMIT_PER_FAMILY = 1_000
DEFAULT_COMPOSITION_HARD_TARGET_LIMIT = 21
DEFAULT_ASTRALBASE_DIR = Path("/Users/devinnicholson/astralbase")
DEFAULT_BITMESH_DIR = Path("/Users/devinnicholson/bitmesh")
DEFAULT_THERMOGRAPH_DIR = Path("/Users/devinnicholson/thermograph")
DISCOVERY_VALUE_RULE = "component_depth2_local_move_game_v0"


def _load_discovery_contract_module():
    module_path = ROOT / "python" / "partizan" / "discovery.py"
    spec = importlib.util.spec_from_file_location(
        "partizan_discovery_contract", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load discovery contracts from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discovery_contract = _load_discovery_contract_module()


class ShardRunnerError(RuntimeError):
    """Raised when the local dataset shard runner cannot complete."""


def _resolve_from_root(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        try:
            return str(Path("..") / resolved.relative_to(ROOT.parent))
        except ValueError:
            return str(resolved)


def _format_command(command: list[str] | tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _run_capture(
    command: tuple[str, ...],
    cwd: Path,
    label: str,
    env: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        raise ShardRunnerError(f"{label} failed with exit code {result.returncode}")
    if result.stderr:
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise ShardRunnerError(f"could not read git HEAD for {_display_path(path)}")
    return result.stdout.strip()


def _git_is_clean(path: Path) -> bool:
    result = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise ShardRunnerError(f"could not inspect Git status for {_display_path(path)}")
    return not result.stdout.strip()


def _immutable_repo_commit(path: Path, label: str) -> str:
    if not path.exists():
        raise ShardRunnerError(f"{label} repository not found: {path}")
    if not _git_is_clean(path):
        raise ShardRunnerError(
            f"{label} repository is dirty; discovery evidence requires an immutable commit"
        )
    commit = _git_head(path)
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ShardRunnerError(f"{label} HEAD is not a full lowercase Git commit")
    return commit


def _raise_contract_errors(label: str, errors: list[str]) -> None:
    if errors:
        raise ShardRunnerError(f"{label} contract failed: {'; '.join(errors)}")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _candidate_artifact_contract_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ShardRunnerError(
            "the frozen candidate artifact must be inside the Partizan repository "
            "or --candidate-artifact-path must provide its repository-relative path"
        ) from error


def _current_discovery_repositories(
    *,
    astralbase_dir: Path = DEFAULT_ASTRALBASE_DIR,
    bitmesh_dir: Path = DEFAULT_BITMESH_DIR,
    thermograph_dir: Path = DEFAULT_THERMOGRAPH_DIR,
    partizan_dir: Path = ROOT,
) -> dict[str, str]:
    return {
        "astralbase": _immutable_repo_commit(astralbase_dir, "astralbase"),
        "bitmesh": _immutable_repo_commit(bitmesh_dir, "bitmesh"),
        "thermograph": _immutable_repo_commit(thermograph_dir, "thermograph"),
        "partizan": _immutable_repo_commit(partizan_dir, "partizan"),
    }


def _load_frozen_discovery_pool(
    target_path: Path,
    proposals_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    try:
        target = discovery_contract.load_json(target_path)
        proposals = discovery_contract.load_jsonl(proposals_path)
        manifest = discovery_contract.load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ShardRunnerError(f"could not load frozen discovery pool: {error}") from error
    _raise_contract_errors(
        "target", discovery_contract.validate_target_spec(target)
    )
    for index, proposal in enumerate(proposals):
        _raise_contract_errors(
            f"proposal[{index}]",
            discovery_contract.validate_candidate_proposal(proposal, target),
        )
    _raise_contract_errors(
        "candidate pool manifest",
        discovery_contract.validate_candidate_pool_manifest(
            manifest, target, proposals, proposals_path
        ),
    )
    return target, proposals, manifest


def freeze_discovery_pool(
    *,
    target_path: Path,
    proposals_input_path: Path,
    proposals_output_path: Path,
    manifest_output_path: Path,
    source_repositories: dict[str, str],
    candidate_artifact_path: str | None = None,
) -> dict[str, Any]:
    """Freeze an existing proposal JSONL; this does not generate candidates."""

    try:
        target = discovery_contract.load_json(target_path)
        proposals = discovery_contract.load_jsonl(proposals_input_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ShardRunnerError(f"could not load discovery inputs: {error}") from error
    _raise_contract_errors("target", discovery_contract.validate_target_spec(target))
    if not proposals:
        raise ShardRunnerError("proposal input must contain at least one candidate")
    maximum = target["search_limits"]["max_pool_size"]
    if len(proposals) > maximum:
        raise ShardRunnerError(
            f"proposal input has {len(proposals)} rows, exceeding max_pool_size={maximum}"
        )
    for index, proposal in enumerate(proposals):
        _raise_contract_errors(
            f"proposal[{index}]",
            discovery_contract.validate_candidate_proposal(proposal, target),
        )

    canonical_first = discovery_contract.canonical_jsonl_bytes(proposals)
    canonical_second = discovery_contract.canonical_jsonl_bytes(proposals)
    if canonical_first != canonical_second:
        raise ShardRunnerError("proposal canonicalization was not byte deterministic")
    artifact_sha = discovery_contract.sha256_hex(canonical_first)

    generator_fields = ("name", "version", "config_sha256", "random_seed")
    first_generator = proposals[0]["generator"]
    generator = {key: first_generator[key] for key in generator_fields}
    for index, proposal in enumerate(proposals[1:], start=1):
        observed = {key: proposal["generator"][key] for key in generator_fields}
        if observed != generator:
            raise ShardRunnerError(
                f"proposal[{index}] does not share the frozen pool generator configuration"
            )
    if first_generator["code_commit"] != source_repositories.get("astralbase"):
        raise ShardRunnerError(
            "proposal generator code_commit does not match frozen Astralbase commit"
        )

    artifact_contract_path = candidate_artifact_path or _candidate_artifact_contract_path(
        proposals_output_path
    )
    manifest: dict[str, Any] = {
        "schema_version": discovery_contract.POOL_SCHEMA_VERSION,
        "pool_id": "pool-sha256:" + "0" * 64,
        "target_ref": {
            "target_id": target["target_id"],
            "sha256": discovery_contract.sha256_hex(
                discovery_contract.canonical_json_bytes(target)
            ),
        },
        "candidate_artifact": {
            "path": artifact_contract_path,
            "schema_version": discovery_contract.PROPOSAL_SCHEMA_VERSION,
            "sha256": artifact_sha,
            "row_count": len(proposals),
        },
        "generator": generator,
        "source_repositories": dict(source_repositories),
        "determinism": {
            "operation": "canonicalization",
            "run_count": 2,
            "byte_identical": True,
            "artifact_sha256": artifact_sha,
        },
        "ranker_boundary": {
            "contract_id": "proposal_only_ranker_input_v0.1",
            "generation_phase": "offline_before_any_verifier_call",
            "allowed_target_paths": ["/ranker_view"],
            "allowed_proposal_paths": ["/position", "/proposal_features"],
            "audit_passed": True,
        },
    }
    manifest["pool_id"] = discovery_contract.candidate_pool_id_for(manifest)

    # Validate in memory before either output becomes authoritative.
    _write_bytes(proposals_output_path, canonical_first)
    errors = discovery_contract.validate_candidate_pool_manifest(
        manifest, target, proposals, proposals_output_path
    )
    if errors:
        proposals_output_path.unlink(missing_ok=True)
        _raise_contract_errors("candidate pool manifest", errors)
    _write_bytes(
        manifest_output_path, discovery_contract.canonical_json_bytes(manifest)
    )
    return manifest


def _astralbase_requests(
    target: dict[str, Any], proposals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        discovery_contract.astralbase_request_for(target, proposal)
        for proposal in proposals
    ]


def _parse_astralbase_responses(
    payload: bytes, proposals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ShardRunnerError("Astralbase response is not UTF-8") from error
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise ShardRunnerError("Astralbase response must be non-empty JSONL without blanks")
    try:
        rows = [json.loads(line) for line in lines]
    except json.JSONDecodeError as error:
        raise ShardRunnerError(f"Astralbase returned invalid JSONL: {error}") from error
    if len(rows) != len(proposals) or not all(isinstance(row, dict) for row in rows):
        raise ShardRunnerError("Astralbase must return exactly one object per proposal")
    expected_ids = [proposal["proposal_id"] for proposal in proposals]
    observed_ids = [row.get("request_id") for row in rows]
    if observed_ids != expected_ids:
        raise ShardRunnerError(
            "Astralbase responses must preserve the frozen proposal order and request IDs"
        )
    return rows


def _certified_actual(response: dict[str, Any], node_budget: int) -> dict[str, Any]:
    actual = response.get("actual")
    required = {
        "identity_kind",
        "semantics",
        "value_class",
        "digest_v1_sha256",
        "legacy_digest",
        "recursive_nodes",
        "decomposition_digest",
        "composition_digest",
        "component_legacy_digests",
    }
    if not isinstance(actual, dict) or not required.issubset(actual):
        raise ShardRunnerError("certified Astralbase response lacks structural evidence")
    recursive_nodes = actual.get("recursive_nodes")
    if (
        not isinstance(recursive_nodes, int)
        or isinstance(recursive_nodes, bool)
        or recursive_nodes < 0
        or recursive_nodes > node_budget
    ):
        raise ShardRunnerError("Astralbase recursive_nodes violates the request node_budget")
    for key in ("digest_v1_sha256", "decomposition_digest", "composition_digest"):
        value = actual.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ShardRunnerError(f"Astralbase actual.{key} is not a SHA-256 digest")
    if actual.get("semantics") != "structural_tree_identity_only":
        raise ShardRunnerError("Astralbase returned unsupported identity semantics")
    return actual


def _translate_astralbase_result(
    *,
    target: dict[str, Any],
    proposal: dict[str, Any],
    response: dict[str, Any],
    source_repositories: dict[str, str],
) -> dict[str, Any]:
    status = response.get("status")
    if status not in {
        "verified_match",
        "verified_nonmatch",
        "rejected",
        "internal_error",
    }:
        raise ShardRunnerError(f"Astralbase returned unsupported status: {status}")
    reason_code = response.get("reason_code")
    if reason_code is not None and (not isinstance(reason_code, str) or not reason_code):
        raise ShardRunnerError("Astralbase reason_code must be a non-empty string or null")

    node_budget = target["search_limits"]["max_recursive_nodes_per_candidate"]
    target_digest = target["target"]["identity_sha256"]
    verifier = {
        "name": "astralbase_target_candidate_verifier",
        "version": "0.1.0",
        "config_sha256": discovery_contract.verifier_config_sha256_for(target),
        "code_commits": dict(source_repositories),
    }
    comparison = {
        "identity_contract": discovery_contract.IDENTITY_CONTRACT,
        "target_identity_sha256": target_digest,
        "observed_identity_sha256": None,
        "matches": None,
    }
    evidence = {
        "label_kind": "rejected",
        "certificate_digest": None,
        "rejection_codes": [reason_code or status],
        "decomposition_digest": None,
        "composition_digest": None,
        "observed_structural_sha256": None,
        "recursive_nodes": None,
    }

    if status in {"verified_match", "verified_nonmatch"}:
        actual = _certified_actual(response, node_budget)
        if actual["identity_kind"] != target["target"]["identity_contract"]:
            raise ShardRunnerError("Astralbase actual identity kind does not match target")
        observed = actual["digest_v1_sha256"]
        class_equal = actual["value_class"] == target["target"]["value_class"]
        digest_equal = observed == target_digest
        expected_match = class_equal and digest_equal
        if (status == "verified_match") != expected_match:
            raise ShardRunnerError(
                "Astralbase status contradicts its value-class and structural-digest identity"
            )
        comparison.update(
            {"observed_identity_sha256": observed, "matches": expected_match}
        )
        evidence = {
            "label_kind": "exact",
            "certificate_digest": "astralbase-actual-sha256:"
            + discovery_contract.sha256_hex(
                discovery_contract.canonical_json_bytes(actual)
            ),
            "rejection_codes": [],
            "decomposition_digest": actual["decomposition_digest"],
            "composition_digest": actual["composition_digest"],
            "observed_structural_sha256": observed,
            "recursive_nodes": actual["recursive_nodes"],
        }
        outcome = "certified_target" if expected_match else "certified_other"
    elif status == "rejected":
        code = reason_code or "astralbase_rejected"
        evidence["rejection_codes"] = [code]
        outcome = "rejected"
    else:
        code = reason_code or "astralbase_internal_error"
        evidence["rejection_codes"] = [code]
        outcome = "error"

    # The gate sequence and every evidence hash are a pure derivation of the
    # lossless response envelope, not a second interpretation maintained here.
    gates = discovery_contract.verifier_gate_rows_for(response, proposal)
    request = discovery_contract.astralbase_request_for(target, proposal)

    result: dict[str, Any] = {
        "schema_version": discovery_contract.RESULT_SCHEMA_VERSION,
        "result_id": "result-sha256:" + "0" * 64,
        "target_id": target["target_id"],
        "proposal_id": proposal["proposal_id"],
        "candidate_key": proposal["candidate_key"],
        "verifier": verifier,
        "verifier_io": {
            "request": request,
            "request_sha256": discovery_contract.sha256_hex(
                discovery_contract.canonical_json_bytes(request)
            ),
            "response": response,
            "response_sha256": discovery_contract.sha256_hex(
                discovery_contract.canonical_json_bytes(response)
            ),
        },
        "gates": gates,
        "outcome": outcome,
        "target_comparison": comparison,
        "evidence": evidence,
    }
    result["result_id"] = discovery_contract.verifier_result_id_for(result)
    _raise_contract_errors(
        "translated verifier result",
        discovery_contract.validate_verifier_result(result, target, proposal),
    )
    return result


def verify_discovery_pool(
    *,
    target_path: Path,
    proposals_path: Path,
    manifest_path: Path,
    results_output_path: Path,
    astralbase_dir: Path = DEFAULT_ASTRALBASE_DIR,
    bitmesh_dir: Path = DEFAULT_BITMESH_DIR,
    thermograph_dir: Path = DEFAULT_THERMOGRAPH_DIR,
    current_repositories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    target, proposals, manifest = _load_frozen_discovery_pool(
        target_path, proposals_path, manifest_path
    )
    astralbase_dir = astralbase_dir.resolve()
    bitmesh_dir = bitmesh_dir.resolve()
    thermograph_dir = thermograph_dir.resolve()
    current = current_repositories or _current_discovery_repositories(
        astralbase_dir=astralbase_dir,
        bitmesh_dir=bitmesh_dir,
        thermograph_dir=thermograph_dir,
    )
    if current != manifest["source_repositories"]:
        raise ShardRunnerError(
            "current repository commits do not match the frozen pool manifest"
        )

    requests = _astralbase_requests(target, proposals)
    with tempfile.TemporaryDirectory(prefix="partizan-discovery-") as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "requests.jsonl"
        request_path.write_bytes(discovery_contract.canonical_jsonl_bytes(requests))
        payload = _run_capture(
            (
                "cargo",
                "--config",
                f'patch."crates-io".bitmesh.path="{bitmesh_dir}"',
                "--config",
                f'patch."crates-io".thermograph.path="{thermograph_dir}"',
                "run",
                "--locked",
                "--offline",
                "--quiet",
                "--",
                "--verify-target-candidates",
                str(request_path),
            ),
            cwd=astralbase_dir,
            label="astralbase discovery verification",
            env={
                **dict(os.environ),
                "CARGO_TARGET_DIR": str(temp_path / "cargo-target"),
            },
        )
    responses = _parse_astralbase_responses(payload, proposals)
    results = [
        _translate_astralbase_result(
            target=target,
            proposal=proposal,
            response=response,
            source_repositories=current,
        )
        for proposal, response in zip(proposals, responses)
    ]
    _write_bytes(
        results_output_path, discovery_contract.canonical_jsonl_bytes(results)
    )
    return results


def replay_discovery_run(
    *,
    target_path: Path,
    proposals_path: Path,
    manifest_path: Path,
    results_path: Path,
    run_output_path: Path,
    verifier_budget: int,
) -> dict[str, Any]:
    target, proposals, manifest = _load_frozen_discovery_pool(
        target_path, proposals_path, manifest_path
    )
    if (
        not isinstance(verifier_budget, int)
        or isinstance(verifier_budget, bool)
        or verifier_budget <= 0
    ):
        raise ShardRunnerError("verifier budget must be a positive integer")
    target_max = target["search_limits"]["max_verifier_calls"]
    if verifier_budget > target_max:
        raise ShardRunnerError("verifier budget exceeds the target search limit")
    if verifier_budget > len(proposals):
        raise ShardRunnerError("verifier budget exceeds the frozen proposal count")
    try:
        results = discovery_contract.load_jsonl(results_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ShardRunnerError(f"could not load verifier results: {error}") from error
    results_by_proposal: dict[str, dict[str, Any]] = {}
    proposals_by_id = {proposal["proposal_id"]: proposal for proposal in proposals}
    for index, result in enumerate(results):
        proposal = proposals_by_id.get(result.get("proposal_id"))
        if proposal is None:
            raise ShardRunnerError(f"result[{index}] references an unknown proposal")
        if proposal["proposal_id"] in results_by_proposal:
            raise ShardRunnerError("verifier results contain a duplicate proposal")
        _raise_contract_errors(
            f"result[{index}]",
            discovery_contract.validate_verifier_result(result, target, proposal),
        )
        results_by_proposal[proposal["proposal_id"]] = result
    if set(results_by_proposal) != set(proposals_by_id):
        raise ShardRunnerError("replay requires exactly one result for every proposal")

    selected = proposals[:verifier_budget]
    calls = []
    selected_results = []
    for index, proposal in enumerate(selected):
        result = results_by_proposal[proposal["proposal_id"]]
        selected_results.append(result)
        calls.append(
            {
                "call_index": index,
                "proposal_id": proposal["proposal_id"],
                "candidate_key": proposal["candidate_key"],
                "score_float_hex": None,
                "result_id": result["result_id"],
            }
        )
    outcomes = [result["outcome"] for result in selected_results]
    first_target = next(
        (index for index, outcome in enumerate(outcomes) if outcome == "certified_target"),
        None,
    )
    run: dict[str, Any] = {
        "schema_version": discovery_contract.RUN_SCHEMA_VERSION,
        "run_id": "run-sha256:" + "0" * 64,
        "target_id": target["target_id"],
        "pool_id": manifest["pool_id"],
        "policy": {
            "policy_id": "input_order_v0",
            "version": "0.1.0",
            "random_seed": 0,
            "checkpoint_sha256": None,
            "candidate_order_sha256": discovery_contract.sha256_hex(
                discovery_contract.canonical_json_bytes(
                    [proposal["proposal_id"] for proposal in proposals]
                )
            ),
        },
        "budget": {
            "max_verifier_calls": verifier_budget,
            "calls_made": len(calls),
        },
        "calls": calls,
        "summary": {
            "calls_made": len(calls),
            "unique_candidates_verified": len(
                {proposal["candidate_key"] for proposal in selected}
            ),
            "outcome_counts": dict(sorted(Counter(outcomes).items())),
            "unique_certified_targets": len(
                {
                    proposal["candidate_key"]
                    for proposal, outcome in zip(selected, outcomes)
                    if outcome == "certified_target"
                }
            ),
            "first_target_call_index": first_target,
            "budget_exhausted": len(calls) == verifier_budget,
        },
    }
    run["run_id"] = discovery_contract.discovery_run_id_for(run)
    _raise_contract_errors(
        "discovery run",
        discovery_contract.validate_discovery_run(
            run, target, manifest, proposals, results
        ),
    )
    _write_bytes(run_output_path, discovery_contract.canonical_json_bytes(run))
    return run


def run_discovery_freeze_pool(args: argparse.Namespace) -> int:
    repositories = _current_discovery_repositories(
        astralbase_dir=args.astralbase_dir.resolve(),
        bitmesh_dir=args.bitmesh_dir.resolve(),
        thermograph_dir=args.thermograph_dir.resolve(),
        partizan_dir=ROOT,
    )
    manifest = freeze_discovery_pool(
        target_path=_resolve_from_root(args.target),
        proposals_input_path=_resolve_from_root(args.proposals),
        proposals_output_path=_resolve_from_root(args.output),
        manifest_output_path=_resolve_from_root(args.manifest),
        source_repositories=repositories,
        candidate_artifact_path=args.candidate_artifact_path,
    )
    print(
        "discovery-freeze-pool: ok "
        f"(pool_id={manifest['pool_id']}, rows={manifest['candidate_artifact']['row_count']})"
    )
    return 0


def run_discovery_verify_pool(args: argparse.Namespace) -> int:
    repositories = _current_discovery_repositories(
        astralbase_dir=args.astralbase_dir.resolve(),
        bitmesh_dir=args.bitmesh_dir.resolve(),
        thermograph_dir=args.thermograph_dir.resolve(),
        partizan_dir=ROOT,
    )
    results = verify_discovery_pool(
        target_path=_resolve_from_root(args.target),
        proposals_path=_resolve_from_root(args.proposals),
        manifest_path=_resolve_from_root(args.manifest),
        results_output_path=_resolve_from_root(args.output),
        astralbase_dir=args.astralbase_dir.resolve(),
        bitmesh_dir=args.bitmesh_dir.resolve(),
        thermograph_dir=args.thermograph_dir.resolve(),
        current_repositories=repositories,
    )
    print(f"discovery-verify-pool: ok (results={len(results)})")
    return 0


def run_discovery_replay(args: argparse.Namespace) -> int:
    run = replay_discovery_run(
        target_path=_resolve_from_root(args.target),
        proposals_path=_resolve_from_root(args.proposals),
        manifest_path=_resolve_from_root(args.manifest),
        results_path=_resolve_from_root(args.results),
        run_output_path=_resolve_from_root(args.output),
        verifier_budget=args.verifier_budget,
    )
    print(
        "discovery-replay-run: ok "
        f"(run_id={run['run_id']}, calls={run['budget']['calls_made']})"
    )
    return 0


def _validate_with_label_schema(path: Path) -> None:
    command = (
        sys.executable,
        str(LABEL_SCHEMA_PATH),
        "validate",
        str(path),
    )
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise ShardRunnerError(
            f"label schema validation failed with exit code {result.returncode}"
        )


def _summarize_jsonl(path: Path) -> dict[str, object]:
    label_kind_counts: Counter[str] = Counter()
    schema_versions: Counter[str] = Counter()
    rejection_status_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    exact_value_class_counts: Counter[str] = Counter()
    exact_solver_scope_counts: Counter[str] = Counter()
    frontier_value_class_counts: Counter[str] = Counter()
    certificate_kind_counts: Counter[str] = Counter()
    position_encoding_counts: Counter[str] = Counter()
    row_id_counts: Counter[str] = Counter()
    position_key_counts: Counter[str] = Counter()
    exact_certificate_digest_counts: Counter[str] = Counter()
    row_count = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row_count += 1
            row = json.loads(line)
            schema_versions.update([str(row.get("schema_version"))])
            row_id_counts.update([str(row.get("row_id"))])
            position = row.get("position", {})
            if isinstance(position, dict):
                encoding = str(position.get("encoding"))
                position_encoding_counts.update([encoding])
                position_key_counts.update(
                    [f"{encoding}:{str(position.get('text'))}"]
                )

            label_kind = str(row.get("label_kind"))
            label_kind_counts.update([label_kind])

            if label_kind == "exact":
                exact = row.get("exact", {})
                if isinstance(exact, dict):
                    exact_value_class_counts.update([str(exact.get("value_class"))])
                    value = exact.get("value", {})
                    if isinstance(value, dict):
                        exact_solver_scope_counts.update(
                            [str(value.get("solver_scope"))]
                        )
                        frontier_value_class = value.get("frontier_value_class")
                        if frontier_value_class:
                            frontier_value_class_counts.update(
                                [str(frontier_value_class)]
                            )
                provenance = row.get("provenance", {})
                if isinstance(provenance, dict):
                    certificate = provenance.get("certificate", {})
                    if isinstance(certificate, dict):
                        certificate_kind_counts.update(
                            [str(certificate.get("kind"))]
                        )
                        digest = certificate.get("digest")
                        if digest:
                            exact_certificate_digest_counts.update([str(digest)])

            if label_kind == "rejected":
                rejected = row.get("rejected", {})
                if isinstance(rejected, dict):
                    rejection_status_counts.update([str(rejected.get("status"))])
                    for reason in rejected.get("reasons", []):
                        reason_text = str(reason)
                        reason_code = reason_text.split(":", 1)[0]
                        rejection_reason_counts.update([reason_code])

    return {
        "row_count": row_count,
        "schema_versions": dict(sorted(schema_versions.items())),
        "label_kind_counts": dict(sorted(label_kind_counts.items())),
        "exact_rows": label_kind_counts.get("exact", 0),
        "rejected_rows": label_kind_counts.get("rejected", 0),
        "exact_value_class_counts": dict(sorted(exact_value_class_counts.items())),
        "exact_solver_scope_counts": dict(sorted(exact_solver_scope_counts.items())),
        "frontier_value_class_counts": dict(sorted(frontier_value_class_counts.items())),
        "certificate_kind_counts": dict(sorted(certificate_kind_counts.items())),
        "position_encoding_counts": dict(sorted(position_encoding_counts.items())),
        "rejection_status_counts": dict(sorted(rejection_status_counts.items())),
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "duplicate_row_ids": duplicate_count(row_id_counts),
        "duplicate_positions": duplicate_count(position_key_counts),
        "duplicate_exact_certificate_digests": duplicate_count(
            exact_certificate_digest_counts
        ),
    }


def duplicate_count(counts: Counter[str]) -> int:
    return sum(count - 1 for count in counts.values() if count > 1)


def _write_manifest(
    manifest_path: Path,
    manifest_title: str,
    manifest_description: str,
    output_path: Path,
    output_sha256: str,
    astralbase_dir: Path,
    astralbase_commit: str,
    generator_command: list[str] | tuple[str, ...],
    runner_command: list[str],
    summary: dict[str, object],
) -> None:
    label_kind_counts = summary["label_kind_counts"]
    exact_value_class_counts = summary["exact_value_class_counts"]
    exact_solver_scope_counts = summary["exact_solver_scope_counts"]
    frontier_value_class_counts = summary["frontier_value_class_counts"]
    certificate_kind_counts = summary["certificate_kind_counts"]
    position_encoding_counts = summary["position_encoding_counts"]
    rejection_status_counts = summary["rejection_status_counts"]
    rejection_reason_counts = summary["rejection_reason_counts"]

    def bullet_counts(counts: dict[str, int]) -> str:
        if not counts:
            return "- none"
        return "\n".join(f"- `{key}`: {value}" for key, value in counts.items())

    manifest = f"""# {manifest_title}

{manifest_description}

## Artifact

- Schema version: `{SCHEMA_VERSION}`
- JSONL artifact: `{_display_path(output_path)}`
- Artifact SHA-256: `{output_sha256}`
- Total rows: {summary["row_count"]}
- Exact rows: {summary["exact_rows"]}
- Rejected rows: {summary["rejected_rows"]}

## Source

- Source repo: `{_display_path(astralbase_dir)}`
- Source commit: `{astralbase_commit}`
- Generator command: `cd {_display_path(astralbase_dir)} && {_format_command(generator_command)}`
- Runner command: `{_format_command(runner_command)}`
- Validator command: `python3 agents/label_schema.py validate {_display_path(output_path)}`
- Determinism check: the runner compares two generator invocations before writing.

## Label Counts

{bullet_counts(label_kind_counts)}

## Exact Value Class Counts

{bullet_counts(exact_value_class_counts)}

## Exact Solver Scope Counts

{bullet_counts(exact_solver_scope_counts)}

## Frontier Value Class Counts

{bullet_counts(frontier_value_class_counts)}

## Certificate Kind Counts

{bullet_counts(certificate_kind_counts)}

## Position Encoding Counts

{bullet_counts(position_encoding_counts)}

## Rejection Counts By Status

{bullet_counts(rejection_status_counts)}

## Rejection Counts By Reason

{bullet_counts(rejection_reason_counts)}

## Leakage And Uniqueness Checks

- Duplicate row IDs: {summary["duplicate_row_ids"]}
- Duplicate positions: {summary["duplicate_positions"]}
- Duplicate exact certificate digests: {summary["duplicate_exact_certificate_digests"]}

## Notes

- Exact rows remain the only rows eligible as exact supervision targets.
- Rejected rows stay in the shard so unsupported inputs are visible and counted.
- The runner injects `ASTRALBASE_CODE_COMMIT` so exact-row provenance and this
  manifest record the same astralbase Git commit.
"""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest, encoding="utf-8")


def _run_astralbase_jsonl_shard(
    args: argparse.Namespace,
    command_name: str,
    generator_command: tuple[str, ...],
    default_output_path: Path,
    default_manifest_path: Path,
    manifest_title: str,
    manifest_description: str,
) -> int:
    astralbase_dir = _resolve_from_root(args.astralbase_dir)
    output_path = _resolve_from_root(args.output)
    manifest_path = _resolve_from_root(args.manifest)

    if not astralbase_dir.exists():
        raise ShardRunnerError(f"astralbase directory not found: {astralbase_dir}")

    astralbase_commit = _git_head(astralbase_dir)
    generator_env = {
        **dict(os.environ),
        "ASTRALBASE_CODE_COMMIT": astralbase_commit,
    }

    first = _run_capture(
        generator_command,
        cwd=astralbase_dir,
        label=f"astralbase {command_name} generation",
        env=generator_env,
    )
    if not args.skip_determinism_check:
        second = _run_capture(
            generator_command,
            cwd=astralbase_dir,
            label=f"astralbase {command_name} determinism check",
            env=generator_env,
        )
        if first != second:
            raise ShardRunnerError(
                f"astralbase {command_name} is not byte-identical across runs"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(first)

    _validate_with_label_schema(output_path)

    output_sha256 = hashlib.sha256(first).hexdigest()
    summary = _summarize_jsonl(output_path)
    runner_command = [
        "python3",
        "engine/orchestrator.py",
        command_name,
        "--astralbase-dir",
        _display_path(astralbase_dir),
    ]
    if getattr(args, "limit", None) is not None and args.limit != DEFAULT_FRONTIER_LIMIT:
        runner_command.extend(["--limit", str(args.limit)])
    if (
        getattr(args, "limit_per_family", None) is not None
        and args.limit_per_family != DEFAULT_FAMILY_FRONTIER_LIMIT_PER_FAMILY
    ):
        runner_command.extend(["--limit-per-family", str(args.limit_per_family)])
    if output_path != default_output_path:
        runner_command.extend(["--output", _display_path(output_path)])
    if manifest_path != default_manifest_path:
        runner_command.extend(["--manifest", _display_path(manifest_path)])
    if args.skip_determinism_check:
        runner_command.append("--skip-determinism-check")

    _write_manifest(
        manifest_path=manifest_path,
        manifest_title=manifest_title,
        manifest_description=manifest_description,
        output_path=output_path,
        output_sha256=output_sha256,
        astralbase_dir=astralbase_dir,
        astralbase_commit=astralbase_commit,
        generator_command=generator_command,
        runner_command=runner_command,
        summary=summary,
    )

    print(
        f"{command_name}: ok "
        f"({_display_path(output_path)}, "
        f"rows={summary['row_count']}, "
        f"exact={summary['exact_rows']}, "
        f"rejected={summary['rejected_rows']})"
    )
    print(f"manifest: {_display_path(manifest_path)}")
    return 0


def run_sample_label_shard(args: argparse.Namespace) -> int:
    return _run_astralbase_jsonl_shard(
        args=args,
        command_name="sample-label-shard",
        generator_command=ASTRALBASE_SHARD_COMMAND,
        default_output_path=DEFAULT_SHARD_PATH,
        default_manifest_path=DEFAULT_MANIFEST_PATH,
        manifest_title="Dataset v0 Manifest",
        manifest_description=(
            "This manifest records the current vertical-slice JSONL shard generated by the\n"
            "local Partizan runner."
        ),
    )


def run_frontier_label_shard(args: argparse.Namespace) -> int:
    generator_command = (
        *ASTRALBASE_FRONTIER_SHARD_BASE_COMMAND,
        "--limit",
        str(args.limit),
    )
    return _run_astralbase_jsonl_shard(
        args=args,
        command_name="frontier-label-shard",
        generator_command=generator_command,
        default_output_path=DEFAULT_FRONTIER_SHARD_PATH,
        default_manifest_path=DEFAULT_FRONTIER_MANIFEST_PATH,
        manifest_title="Frontier Wave 06 Manifest",
        manifest_description=(
            "This manifest records the deterministic KQK terminal-frontier JSONL shard\n"
            "generated for Wave 6 scale-up validation."
        ),
    )


def run_family_frontier_label_shard(args: argparse.Namespace) -> int:
    generator_command = (
        *ASTRALBASE_FAMILY_FRONTIER_SHARD_BASE_COMMAND,
        "--limit-per-family",
        str(args.limit_per_family),
    )
    return _run_astralbase_jsonl_shard(
        args=args,
        command_name="family-frontier-label-shard",
        generator_command=generator_command,
        default_output_path=DEFAULT_FAMILY_FRONTIER_SHARD_PATH,
        default_manifest_path=DEFAULT_FAMILY_FRONTIER_MANIFEST_PATH,
        manifest_title="Family Frontier Wave 07 Manifest",
        manifest_description=(
            "This manifest records the deterministic KQK+KRK terminal-frontier JSONL shard\n"
            "generated for Wave 7 generator-family split validation."
        ),
    )


def run_expanded_family_frontier_label_shard(args: argparse.Namespace) -> int:
    generator_command = (
        *ASTRALBASE_EXPANDED_FAMILY_FRONTIER_SHARD_BASE_COMMAND,
        "--limit-per-family",
        str(args.limit_per_family),
    )
    return _run_astralbase_jsonl_shard(
        args=args,
        command_name="expanded-family-frontier-label-shard",
        generator_command=generator_command,
        default_output_path=DEFAULT_EXPANDED_FAMILY_FRONTIER_SHARD_PATH,
        default_manifest_path=DEFAULT_EXPANDED_FAMILY_FRONTIER_MANIFEST_PATH,
        manifest_title="Expanded Family Frontier Wave 12 Manifest",
        manifest_description=(
            "This manifest records the deterministic KQK+KRK+KBK+KNK frontier JSONL\n"
            "shard generated for Wave 12 material-family breadth validation."
        ),
    )


def run_composition_hard_target_shard(args: argparse.Namespace) -> int:
    generator_command = (
        *ASTRALBASE_COMPOSITION_HARD_TARGET_SHARD_BASE_COMMAND,
        "--limit",
        str(args.limit),
    )
    return _run_astralbase_jsonl_shard(
        args=args,
        command_name="composition-hard-target-shard",
        generator_command=generator_command,
        default_output_path=DEFAULT_COMPOSITION_HARD_TARGET_SHARD_PATH,
        default_manifest_path=DEFAULT_COMPOSITION_HARD_TARGET_MANIFEST_PATH,
        manifest_title="Composition Hard Target Wave 17 Manifest",
        manifest_description=(
            "This manifest records the deterministic Wave 17 composition-certificate\n"
            "hard-target JSONL shard generated from the astralbase BMCOMPOSE fixture."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Partizan local orchestration tools.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    shard_parser = subcommands.add_parser(
        "sample-label-shard",
        help="Generate, validate, and record the current dataset-label shard.",
    )
    shard_parser.add_argument(
        "--astralbase-dir",
        type=Path,
        required=True,
        help="Explicit path to an Astralbase 0.1.0 source checkout.",
    )
    shard_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SHARD_PATH,
        help="JSONL artifact path to write.",
    )
    shard_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Dataset manifest path to write.",
    )
    shard_parser.add_argument(
        "--skip-determinism-check",
        action="store_true",
        help="Run the astralbase generator once instead of comparing two runs.",
    )

    frontier_parser = subcommands.add_parser(
        "frontier-label-shard",
        help="Generate, validate, and record the Wave 6 KQK frontier shard.",
    )
    frontier_parser.add_argument(
        "--astralbase-dir",
        type=Path,
        required=True,
        help="Explicit path to an Astralbase 0.1.0 source checkout.",
    )
    frontier_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_FRONTIER_LIMIT,
        help="Number of frontier rows to write.",
    )
    frontier_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FRONTIER_SHARD_PATH,
        help="JSONL artifact path to write.",
    )
    frontier_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_FRONTIER_MANIFEST_PATH,
        help="Frontier dataset manifest path to write.",
    )
    frontier_parser.add_argument(
        "--skip-determinism-check",
        action="store_true",
        help="Run the astralbase generator once instead of comparing two runs.",
    )

    family_parser = subcommands.add_parser(
        "family-frontier-label-shard",
        help="Generate, validate, and record the Wave 7 KQK+KRK frontier shard.",
    )
    family_parser.add_argument(
        "--astralbase-dir",
        type=Path,
        required=True,
        help="Explicit path to an Astralbase 0.1.0 source checkout.",
    )
    family_parser.add_argument(
        "--limit-per-family",
        type=int,
        default=DEFAULT_FAMILY_FRONTIER_LIMIT_PER_FAMILY,
        help="Number of frontier rows to write for each material family.",
    )
    family_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FAMILY_FRONTIER_SHARD_PATH,
        help="JSONL artifact path to write.",
    )
    family_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_FAMILY_FRONTIER_MANIFEST_PATH,
        help="Family frontier dataset manifest path to write.",
    )
    family_parser.add_argument(
        "--skip-determinism-check",
        action="store_true",
        help="Run the astralbase generator once instead of comparing two runs.",
    )

    expanded_family_parser = subcommands.add_parser(
        "expanded-family-frontier-label-shard",
        help="Generate, validate, and record the Wave 12 KQK+KRK+KBK+KNK shard.",
    )
    expanded_family_parser.add_argument(
        "--astralbase-dir",
        type=Path,
        required=True,
        help="Explicit path to an Astralbase 0.1.0 source checkout.",
    )
    expanded_family_parser.add_argument(
        "--limit-per-family",
        type=int,
        default=DEFAULT_FAMILY_FRONTIER_LIMIT_PER_FAMILY,
        help="Number of frontier rows to write for each material family.",
    )
    expanded_family_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EXPANDED_FAMILY_FRONTIER_SHARD_PATH,
        help="JSONL artifact path to write.",
    )
    expanded_family_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_EXPANDED_FAMILY_FRONTIER_MANIFEST_PATH,
        help="Expanded family frontier dataset manifest path to write.",
    )
    expanded_family_parser.add_argument(
        "--skip-determinism-check",
        action="store_true",
        help="Run the astralbase generator once instead of comparing two runs.",
    )

    composition_parser = subcommands.add_parser(
        "composition-hard-target-shard",
        help="Generate, validate, and record the Wave 17 composition hard-target shard.",
    )
    composition_parser.add_argument(
        "--astralbase-dir",
        type=Path,
        required=True,
        help="Explicit path to an Astralbase 0.1.0 source checkout.",
    )
    composition_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_COMPOSITION_HARD_TARGET_LIMIT,
        help="Number of composition hard-target rows to write.",
    )
    composition_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_COMPOSITION_HARD_TARGET_SHARD_PATH,
        help="JSONL artifact path to write.",
    )
    composition_parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_COMPOSITION_HARD_TARGET_MANIFEST_PATH,
        help="Composition hard-target dataset manifest path to write.",
    )
    composition_parser.add_argument(
        "--skip-determinism-check",
        action="store_true",
        help="Run the astralbase generator once instead of comparing two runs.",
    )

    freeze_parser = subcommands.add_parser(
        "discovery-freeze-pool",
        help=(
            "Validate and canonically freeze an already-generated proposal JSONL; "
            "this command does not generate candidates."
        ),
    )
    freeze_parser.add_argument("--target", type=Path, required=True)
    freeze_parser.add_argument(
        "--proposals", type=Path, required=True, help="Existing proposal JSONL."
    )
    freeze_parser.add_argument(
        "--output", type=Path, required=True, help="Canonical proposal JSONL output."
    )
    freeze_parser.add_argument("--manifest", type=Path, required=True)
    freeze_parser.add_argument(
        "--candidate-artifact-path",
        help=(
            "Repository-relative artifact path recorded in the manifest; inferred "
            "from --output when that file is inside Partizan."
        ),
    )
    freeze_parser.add_argument(
        "--astralbase-dir", type=Path, default=DEFAULT_ASTRALBASE_DIR
    )
    freeze_parser.add_argument("--bitmesh-dir", type=Path, default=DEFAULT_BITMESH_DIR)
    freeze_parser.add_argument(
        "--thermograph-dir", type=Path, default=DEFAULT_THERMOGRAPH_DIR
    )

    verify_parser = subcommands.add_parser(
        "discovery-verify-pool",
        help="Verify a valid frozen proposal pool with Astralbase.",
    )
    verify_parser.add_argument("--target", type=Path, required=True)
    verify_parser.add_argument("--proposals", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument(
        "--astralbase-dir", type=Path, default=DEFAULT_ASTRALBASE_DIR
    )
    verify_parser.add_argument("--bitmesh-dir", type=Path, default=DEFAULT_BITMESH_DIR)
    verify_parser.add_argument(
        "--thermograph-dir", type=Path, default=DEFAULT_THERMOGRAPH_DIR
    )

    replay_parser = subcommands.add_parser(
        "discovery-replay-run",
        help="Replay frozen verifier results under deterministic input-order policy.",
    )
    replay_parser.add_argument("--target", type=Path, required=True)
    replay_parser.add_argument("--proposals", type=Path, required=True)
    replay_parser.add_argument("--manifest", type=Path, required=True)
    replay_parser.add_argument("--results", type=Path, required=True)
    replay_parser.add_argument("--output", type=Path, required=True)
    replay_parser.add_argument("--verifier-budget", type=int, required=True)

    return parser


def cli_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "discovery-freeze-pool":
            return run_discovery_freeze_pool(args)
        if args.command == "discovery-verify-pool":
            return run_discovery_verify_pool(args)
        if args.command == "discovery-replay-run":
            return run_discovery_replay(args)
        if args.command == "sample-label-shard":
            return run_sample_label_shard(args)
        if args.command == "frontier-label-shard":
            if args.limit < 0:
                raise ShardRunnerError("--limit must be non-negative")
            return run_frontier_label_shard(args)
        if args.command == "family-frontier-label-shard":
            if args.limit_per_family < 0:
                raise ShardRunnerError("--limit-per-family must be non-negative")
            return run_family_frontier_label_shard(args)
        if args.command == "expanded-family-frontier-label-shard":
            if args.limit_per_family < 0:
                raise ShardRunnerError("--limit-per-family must be non-negative")
            return run_expanded_family_frontier_label_shard(args)
        if args.command == "composition-hard-target-shard":
            if args.limit < 0:
                raise ShardRunnerError("--limit must be non-negative")
            return run_composition_hard_target_shard(args)
    except ShardRunnerError as error:
        print(f"{args.command}: error: {error}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli_main())
