"""Freeze and validate the Wave 69-R six-target Gate C pre-result suite.

The public freezer has no verifier or result command.  It first generates a
target-free board stream twice, then projects the frozen stream to construction
certificates and target-bound proposals in two further Python processes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_PATH = ROOT / "python/partizan/discovery.py"
BASELINES_PATH = ROOT / "python/partizan/discovery_baselines.py"
GATE_S_PATH = ROOT / "python/partizan/gate_s.py"
DEFAULT_REGISTRY = ROOT / "docs/discovery_targets/wave_69_target_registry.v0.1.json"
DEFAULT_PREREGISTRATION = ROOT / "docs/discovery_wave_69r_preregistration.md"
DEFAULT_CATALOG = ROOT / "docs/discovery_wave_69r_construction_catalog.v0.2.json"
DEFAULT_OUTPUT_ROOT = ROOT / "data/discovery/wave_69r/calibration/inputs"
DEFAULT_ORCHESTRATOR = ROOT / "engine/orchestrator.py"

SCHEMA_VERSION = "partizan.wave69r_gate_c_suite.v0.1"
POLICY_SCHEMA_VERSION = "partizan.wave69r_policy_orders.v0.1"
GATE_S_EVIDENCE_SCHEMA_VERSION = "partizan.wave69r_structural_supply_evidence.v0.1"
GATE_S_AUDIT_CONTRACT = "partizan.wave69r_structural_supply_audit.v0.1"
TARGET_COUNT = 6
POOL_SIZE = 1024
RANDOM_REPLICATES = 1000
CALIBRATION_SEED_DOMAIN = b"partizan/w69r/calibration/v1\0"
RANDOM_SEED_DOMAIN = b"partizan/w69r/random/v1\0"
SYNTHETIC_SEED_DOMAIN = b"partizan/test/w69r/gate-c/v1\0"
IMPLEMENTATION_PARENT = "6ddd22af4adb7ff8f6f4c361a9132720a47e87b7"
PINNED_EXTERNAL_COMMITS = {
    "astralbase": "1434fca1fc04d97798ec1b820c56f52f8014ccc7",
    "bitmesh": "ade3417a007b9c8392d8a153abc4b3ed23edf0aa",
    "thermograph": "1d9b6b01c3921aca8c2a8fb13972fee8a4de5041",
}
IMPLEMENTATION_COMPONENT_PATHS = (
    "agents/waves/wave_69r_proof_carrying_generator_repair.json",
    "docs/discovery_wave_69r_preregistration.md",
    "docs/discovery_wave_69r_constructive_grammar_spec.md",
    "docs/discovery_wave_69r_construction_catalog.v0.2.json",
    "docs/discovery_targets/wave_69_target_registry.v0.1.json",
    "docs/schemas/partizan-candidate-board-stream-v0.1.schema.json",
    "docs/schemas/partizan-candidate-generation-receipt-v0.2.schema.json",
    "docs/schemas/partizan-candidate-pool-manifest-v0.3.schema.json",
    "docs/schemas/partizan-dfile-two-component-constructive-catalog-v0.2.schema.json",
    "docs/schemas/partizan-structural-construction-certificate-v0.1.schema.json",
    "docs/schemas/partizan-wave69r-gate-c-suite-v0.1.schema.json",
    "docs/schemas/partizan-wave69r-policy-orders-v0.1.schema.json",
    "python/partizan/wave69r_gate_c_suite.py",
    "scripts/freeze_wave69r_gate_c_suite.py",
    "python/partizan/wave69r_gate_c_evidence.py",
    "scripts/run_wave69r_gate_c_evidence.py",
    "docs/schemas/partizan-wave69r-gate-c-evidence-v0.1.schema.json",
    "python/partizan/discovery.py",
    "python/partizan/discovery_baselines.py",
    "engine/orchestrator.py",
)
EXPECTED_TARGET_IDS = (
    "target-sha256:052f4191fdcbb6fa45716b97cc85949f8c2287c75d532893084955ab7c666122",
    "target-sha256:07de65c35e848be61c6f96872b1b20f3a101efa9b461750c502060842599e0c6",
    "target-sha256:8ceee173bf9c9f8e498a058ba15e2d6e4d37ec3ce0b2b7caf8607ac63744ab5b",
    "target-sha256:41bb336e2bee89d4bdf6b5b7a9d9e1c3c8e1fd27da111dbaecac18ae9e553d6a",
    "target-sha256:73492503d817eb3406951fa9fbe127e8f362401b7d9d695163d7e0c4b1ecdc00",
    "target-sha256:f1b5c956d7454a2a939ed8e3a780a7baca58b2b5cddd44313db6f79b2fc20256",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

SUITE_KEYS = {
    "schema_version",
    "suite_id",
    "phase",
    "registry_ref",
    "preregistration_ref",
    "gate_s_go_ref",
    "implementation",
    "temporal_boundary",
    "source_repositories",
    "seed_contract",
    "policy_contract",
    "target_count",
    "proposal_count_per_target",
    "targets",
    "freeze_boundary",
}
TARGET_KEYS = {
    "target_id",
    "family",
    "bin_index",
    "calibration_seed",
    "target_ref",
    "board_stream_ref",
    "construction_certificates_ref",
    "proposals_ref",
    "generation_receipt_ref",
    "pool_manifest_ref",
    "policy_orders_ref",
}


class GateCSuiteError(ValueError):
    """Raised before any target verifier can be reached."""


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discovery = _load_module(DISCOVERY_PATH, "partizan_wave69r_gate_c_discovery")
baselines = _load_module(BASELINES_PATH, "partizan_wave69r_gate_c_baselines")
gate_s = _load_module(GATE_S_PATH, "partizan_wave69r_gate_c_gate_s")


def canonical_bytes(value: Any) -> bytes:
    return discovery.canonical_json_bytes(value)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity(prefix: str, value: dict[str, Any], key: str) -> str:
    payload = {name: item for name, item in value.items() if name != key}
    return f"{prefix}-sha256:{sha256_hex(canonical_bytes(payload))}"


def suite_id_for(value: dict[str, Any]) -> str:
    return _identity("suite", value, "suite_id")


def policy_orders_id_for(value: dict[str, Any]) -> str:
    return _identity("policy-orders", value, "policy_orders_id")


def calibration_seed(target_id: str, *, domain: bytes = CALIBRATION_SEED_DOMAIN) -> int:
    if re.fullmatch(r"target-sha256:[0-9a-f]{64}", target_id) is None:
        raise GateCSuiteError("calibration seed requires a typed target id")
    return int.from_bytes(
        hashlib.sha256(domain + target_id.encode("ascii")).digest()[:8], "big"
    )


def random_order_seed(
    pool_id: str, replicate: int, *, domain: bytes = RANDOM_SEED_DOMAIN
) -> int:
    if re.fullmatch(r"pool-sha256:[0-9a-f]{64}", pool_id) is None:
        raise GateCSuiteError("random seed requires a typed pool id")
    if not isinstance(replicate, int) or isinstance(replicate, bool) or replicate < 0:
        raise GateCSuiteError("random replicate must be non-negative")
    payload = domain + pool_id.encode("ascii") + b"\0" + str(replicate).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _strict(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateCSuiteError(f"{path}: must be an object")
    if set(value) != keys:
        raise GateCSuiteError(
            f"{path}: keys differ; missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )
    return value


def _repo_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise GateCSuiteError(f"artifact is outside repository root: {path}") from error
    if not relative.parts:
        raise GateCSuiteError("artifact path cannot name repository root")
    return PurePosixPath(*relative.parts).as_posix()


def _resolve_ref(path: Any, root: Path) -> Path:
    if not isinstance(path, str) or not path:
        raise GateCSuiteError("artifact reference path must be non-empty")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
        raise GateCSuiteError(f"invalid repository-relative artifact path: {path}")
    resolved = (root.resolve(strict=True) / Path(*parsed.parts)).resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise GateCSuiteError(f"artifact reference escapes repository: {path}") from error
    return resolved


def _load_json(path: Path, *, canonical: bool = True) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateCSuiteError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise GateCSuiteError(f"{path}: must contain a JSON object")
    if canonical and payload != canonical_bytes(value):
        raise GateCSuiteError(f"{path}: bytes are not canonical JSON")
    return value, payload


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
        lines = payload.decode("utf-8").splitlines()
        if not lines or any(not line for line in lines):
            raise ValueError("JSONL must be non-empty without blank rows")
        rows = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise GateCSuiteError(f"cannot load JSONL {path}: {error}") from error
    if not all(isinstance(row, dict) for row in rows):
        raise GateCSuiteError(f"{path}: every JSONL row must be an object")
    if payload != discovery.canonical_jsonl_bytes(rows):
        raise GateCSuiteError(f"{path}: bytes are not canonical JSONL")
    return rows, payload


def _artifact_ref(
    path: Path,
    root: Path,
    *,
    schema_version: str,
    row_count: int | None = None,
    id_key: str | None = None,
    identifier: str | None = None,
    reference_path: Path | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "path": _repo_relative(reference_path or path, root),
        "schema_version": schema_version,
        "sha256": sha256_hex(path.read_bytes()),
    }
    if row_count is not None:
        value["row_count"] = row_count
    if id_key is not None:
        value[id_key] = identifier
    return value


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise GateCSuiteError(
            f"git {' '.join(arguments)} failed in {repo}: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result.stdout


def clean_commit(repo: Path, name: str) -> str:
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if HEX40.fullmatch(commit) is None:
        raise GateCSuiteError(f"{name}: HEAD is not a full commit")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise GateCSuiteError(f"{name}: repository must be clean")
    return commit


def _require_direct_child(repo: Path, child: str, parent: str, label: str) -> None:
    lineage = _git(repo, "rev-list", "--parents", "-n", "1", child).decode(
        "ascii"
    ).split()
    if lineage != [child, parent]:
        raise GateCSuiteError(f"{label} must be a direct child")


def _require_exact_commit_inventory(
    repo: Path, *, commit: str, expected_paths: Iterable[str], label: str
) -> None:
    expected = sorted(set(expected_paths))
    changed = sorted(
        line
        for line in _git(
            repo,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        )
        .decode("utf-8")
        .splitlines()
        if line
    )
    if changed != expected:
        raise GateCSuiteError(f"{label} commit diff inventory mismatch")
    for relative in expected:
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            raise GateCSuiteError(f"{label} artifact is not a regular file: {relative}")
        if _git(repo, "show", f"{commit}:{relative}") != path.read_bytes():
            raise GateCSuiteError(f"{label} committed bytes mismatch: {relative}")


def load_exact_stage_a_targets(registry_path: Path) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    registry, payload = _load_json(registry_path)
    targets = [item for item in registry.get("targets", []) if item.get("stage") == "stage_a"]
    observed = tuple(item.get("target_spec", {}).get("target_id") for item in targets)
    if observed != EXPECTED_TARGET_IDS:
        raise GateCSuiteError("registry Stage A target ids differ from immutable Wave 69 set")
    if len(targets) != TARGET_COUNT:
        raise GateCSuiteError("registry must provide exactly six Stage A targets")
    if sorted(Counter(item.get("family") for item in targets).values()) != [2, 2, 2]:
        raise GateCSuiteError("registry must provide two targets per family")
    for index, item in enumerate(targets):
        if item.get("bin", {}).get("index") not in {0, 3}:
            raise GateCSuiteError(f"registry target[{index}] has invalid bin")
        errors = discovery.validate_target_spec(item.get("target_spec"))
        if errors:
            raise GateCSuiteError(f"registry target[{index}] invalid: {'; '.join(errors)}")
    return registry, payload, targets


def _order_commitment(
    *, target_id: str, pool_id: str, policy: str, replicate: int | None,
    seed: int | None, ordered_ids: list[str]
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "order_id": "policy-order-sha256:" + "0" * 64,
        "policy": policy,
        "replicate": replicate,
        "seed": seed,
        "ordered_proposal_ids_sha256": sha256_hex(canonical_bytes(ordered_ids)),
        "proposal_count": len(ordered_ids),
        "target_id": target_id,
        "pool_id": pool_id,
    }
    row["order_id"] = _identity("policy-order", row, "order_id")
    return row


def build_policy_orders(
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    seed_domain: bytes = RANDOM_SEED_DOMAIN,
    replicates: int = RANDOM_REPLICATES,
) -> dict[str, Any]:
    proposal_ids = [str(row["proposal_id"]) for row in proposals]
    if len(set(proposal_ids)) != len(proposal_ids):
        raise GateCSuiteError("policy input proposal ids must be unique")
    target_id = str(target["target_id"])
    pool_id = str(pool["pool_id"])
    orders = []
    for replicate in range(replicates):
        seed = random_order_seed(pool_id, replicate, domain=seed_domain)
        ordered = baselines.stable_random_permutation(proposal_ids, seed)
        orders.append(
            _order_commitment(
                target_id=target_id,
                pool_id=pool_id,
                policy="random",
                replicate=replicate,
                seed=seed,
                ordered_ids=ordered,
            )
        )
    heuristic = baselines.heuristic_order(proposals)
    artifact: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_orders_id": "policy-orders-sha256:" + "0" * 64,
        "target_id": target_id,
        "pool_id": pool_id,
        "proposal_artifact": {
            "schema_version": discovery.PROPOSAL_SCHEMA_VERSION,
            "sha256": sha256_hex(discovery.canonical_jsonl_bytes(proposals)),
            "row_count": len(proposals),
        },
        "freeze_boundary": "before_any_verifier_result",
        "random_policy": {
            "version": "partizan.random_permutation.v1",
            "replicate_count": replicates,
            "seed_derivation": (
                'first_u64_be_sha256("partizan/w69r/random/v1\\0" || pool_id '
                '|| "\\0" || ascii_decimal_replicate)'
                if seed_domain == RANDOM_SEED_DOMAIN
                else "synthetic_test_seed_domain"
            ),
            "permutation_algorithm": "splitmix64_rejection_fisher_yates_v1",
            "orders": orders,
        },
        "heuristic_policy": {
            "version": baselines.HEURISTIC_POLICY_VERSION,
            "formula": baselines.HEURISTIC_FORMULA,
            "features": list(baselines.HEURISTIC_FEATURES),
            "sort_direction": "score_descending",
            "tie_break": baselines.TIE_BREAK,
            "order": _order_commitment(
                target_id=target_id,
                pool_id=pool_id,
                policy="fixed_heuristic",
                replicate=None,
                seed=None,
                ordered_ids=heuristic,
            ),
        },
    }
    artifact["policy_orders_id"] = policy_orders_id_for(artifact)
    return artifact


def validate_policy_orders(
    artifact: dict[str, Any],
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    production: bool = True,
) -> None:
    _strict(
        artifact,
        {"schema_version", "policy_orders_id", "target_id", "pool_id", "proposal_artifact", "freeze_boundary", "random_policy", "heuristic_policy"},
        "policy_orders",
    )
    if artifact.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise GateCSuiteError("policy_orders: invalid schema")
    if artifact.get("policy_orders_id") != policy_orders_id_for(artifact):
        raise GateCSuiteError("policy_orders: identity mismatch")
    if artifact.get("target_id") != target.get("target_id") or artifact.get("pool_id") != pool.get("pool_id"):
        raise GateCSuiteError("policy_orders: target or pool mismatch")
    if artifact.get("freeze_boundary") != "before_any_verifier_result":
        raise GateCSuiteError("policy_orders: invalid freeze boundary")
    proposal_sha = sha256_hex(discovery.canonical_jsonl_bytes(proposals))
    if artifact.get("proposal_artifact") != {
        "schema_version": discovery.PROPOSAL_SCHEMA_VERSION,
        "sha256": proposal_sha,
        "row_count": len(proposals),
    }:
        raise GateCSuiteError("policy_orders: proposal artifact mismatch")
    random_policy = _strict(
        artifact.get("random_policy"),
        {"version", "replicate_count", "seed_derivation", "permutation_algorithm", "orders"},
        "policy_orders.random_policy",
    )
    expected_replicates = RANDOM_REPLICATES if production else random_policy.get("replicate_count")
    if random_policy.get("version") != "partizan.random_permutation.v1" or random_policy.get("permutation_algorithm") != "splitmix64_rejection_fisher_yates_v1":
        raise GateCSuiteError("policy_orders: random algorithm mismatch")
    expected_seed_derivation = (
        'first_u64_be_sha256("partizan/w69r/random/v1\\0" || pool_id '
        '|| "\\0" || ascii_decimal_replicate)'
        if production
        else "synthetic_test_seed_domain"
    )
    if random_policy.get("seed_derivation") != expected_seed_derivation:
        raise GateCSuiteError("policy_orders: random seed derivation mismatch")
    if expected_replicates != random_policy.get("replicate_count"):
        raise GateCSuiteError("policy_orders: random replicate count mismatch")
    orders = random_policy.get("orders")
    if not isinstance(orders, list) or len(orders) != expected_replicates:
        raise GateCSuiteError("policy_orders: random orders missing")
    proposal_ids = [row["proposal_id"] for row in proposals]
    for replicate, row in enumerate(orders):
        seed = random_order_seed(str(pool["pool_id"]), replicate)
        if not production:
            seed = row.get("seed")
        expected_ids = baselines.stable_random_permutation(proposal_ids, seed)
        expected = _order_commitment(
            target_id=str(target["target_id"]), pool_id=str(pool["pool_id"]),
            policy="random", replicate=replicate, seed=seed, ordered_ids=expected_ids,
        )
        if row != expected:
            raise GateCSuiteError(f"policy_orders: random order[{replicate}] mismatch")
    heuristic = artifact.get("heuristic_policy")
    expected_heuristic = {
        "version": baselines.HEURISTIC_POLICY_VERSION,
        "formula": baselines.HEURISTIC_FORMULA,
        "features": list(baselines.HEURISTIC_FEATURES),
        "sort_direction": "score_descending",
        "tie_break": baselines.TIE_BREAK,
        "order": _order_commitment(
            target_id=str(target["target_id"]), pool_id=str(pool["pool_id"]),
            policy="fixed_heuristic", replicate=None, seed=None,
            ordered_ids=baselines.heuristic_order(proposals),
        ),
    }
    if heuristic != expected_heuristic:
        raise GateCSuiteError("policy_orders: fixed heuristic mismatch")


def validate_gate_s_go(
    evidence: dict[str, Any], *, implementation_commit: str,
    source_repositories: dict[str, str], evidence_commit: str
) -> None:
    _strict(
        evidence,
        {"schema_version", "evidence_id", "audit_contract", "decision", "implementation_commit", "supply_pre_result", "source_repositories", "checker", "executions", "audit"},
        "gate_s_evidence",
    )
    if evidence.get("schema_version") != GATE_S_EVIDENCE_SCHEMA_VERSION:
        raise GateCSuiteError("Gate S evidence schema mismatch")
    if evidence.get("evidence_id") != _identity("evidence", evidence, "evidence_id"):
        raise GateCSuiteError("Gate S evidence identity mismatch")
    if evidence.get("audit_contract") != GATE_S_AUDIT_CONTRACT:
        raise GateCSuiteError("Gate S audit contract mismatch")
    if evidence.get("decision") != "GO":
        raise GateCSuiteError("Gate C remains closed without Gate S GO")
    if evidence.get("implementation_commit") != implementation_commit:
        raise GateCSuiteError("Gate S implementation commit mismatch")
    if HEX40.fullmatch(evidence_commit) is None:
        raise GateCSuiteError("Gate S evidence commit must be externally supplied")
    if evidence.get("source_repositories") != source_repositories:
        raise GateCSuiteError("Gate S source repositories mismatch")
    if any(HEX40.fullmatch(str(value)) is None for value in source_repositories.values()):
        raise GateCSuiteError("Gate S source repository commit is invalid")

    def bound_ref(reference: dict[str, Any], path: str) -> None:
        ref_path = reference.get("path")
        if (
            not isinstance(ref_path, str)
            or not ref_path
            or PurePosixPath(ref_path).is_absolute()
            or ".." in PurePosixPath(ref_path).parts
            or "\\" in ref_path
        ):
            raise GateCSuiteError(f"{path}.path is not repository-relative")
        if HEX64.fullmatch(str(reference.get("sha256"))) is None:
            raise GateCSuiteError(f"{path}.sha256 is invalid")
    supply = _strict(
        evidence.get("supply_pre_result"),
        {"commit", "manifest", "checker_request_ref", "construction_certificate_inventory"},
        "gate_s_evidence.supply_pre_result",
    )
    if HEX40.fullmatch(str(supply.get("commit"))) is None:
        raise GateCSuiteError("Gate S supply pre-result commit is invalid")
    manifest_ref = _strict(
        supply.get("manifest"),
        {"path", "schema_version", "sha256"},
        "gate_s_evidence.supply_pre_result.manifest",
    )
    if manifest_ref.get("schema_version") != "partizan.wave69r_structural_supply_suite.v0.1":
        raise GateCSuiteError("Gate S supply manifest schema mismatch")
    bound_ref(manifest_ref, "gate_s_evidence.supply_pre_result.manifest")
    request_ref = _strict(
        supply.get("checker_request_ref"),
        {"path", "schema_version", "row_count", "sha256"},
        "gate_s_evidence.supply_pre_result.checker_request_ref",
    )
    if request_ref.get("schema_version") != "partizan.wave69r_structural_supply_request.v0.1" or request_ref.get("row_count") != 4096:
        raise GateCSuiteError("Gate S checker request binding mismatch")
    bound_ref(request_ref, "gate_s_evidence.supply_pre_result.checker_request_ref")
    certificate_inventory = _strict(
        supply.get("construction_certificate_inventory"),
        {"schema_version", "shard_count", "row_count", "references_sha256", "canonical_jsonl_sha256"},
        "gate_s_evidence.supply_pre_result.construction_certificate_inventory",
    )
    if certificate_inventory.get("schema_version") != "partizan.structural_construction_certificate.v0.1" or certificate_inventory.get("shard_count") != 4 or certificate_inventory.get("row_count") != 4096 or HEX64.fullmatch(str(certificate_inventory.get("references_sha256"))) is None or HEX64.fullmatch(str(certificate_inventory.get("canonical_jsonl_sha256"))) is None:
        raise GateCSuiteError("Gate S construction-certificate inventory mismatch")
    checker = _strict(
        evidence.get("checker"),
        {"name", "version", "manifest", "lock", "source", "wrapper", "bitmesh_crate_version", "bitmesh_source_commit", "proof_api"},
        "gate_s_evidence.checker",
    )
    if checker.get("name") != "partizan_gate_s_checker" or checker.get("version") != "0.1.0" or checker.get("bitmesh_crate_version") != "0.1.0" or checker.get("bitmesh_source_commit") != PINNED_EXTERNAL_COMMITS["bitmesh"] or checker.get("proof_api") != "bitmesh:conservative_legal_independence:v0":
        raise GateCSuiteError("Gate S checker provenance mismatch")
    for name in ("manifest", "lock", "source", "wrapper"):
        checker_ref = _strict(checker.get(name), {"path", "sha256"}, f"gate_s_evidence.checker.{name}")
        bound_ref(checker_ref, f"gate_s_evidence.checker.{name}")
    executions = _strict(
        evidence.get("executions"),
        {"mode", "run_count", "primary_ledger", "replay_ledger", "byte_identical"},
        "gate_s_evidence.executions",
    )
    if executions.get("mode") != "separate_checker_processes_v1" or executions.get("run_count") != 2 or executions.get("byte_identical") is not True:
        raise GateCSuiteError("Gate S execution replay mismatch")
    ledgers = []
    for name in ("primary_ledger", "replay_ledger"):
        ledger = _strict(
            executions.get(name),
            {"path", "schema_version", "row_count", "sha256"},
            f"gate_s_evidence.executions.{name}",
        )
        if ledger.get("schema_version") != "partizan.wave69r_structural_supply_result.v0.1" or ledger.get("row_count") != 4096:
            raise GateCSuiteError("Gate S ledger binding mismatch")
        bound_ref(ledger, f"gate_s_evidence.executions.{name}")
        ledgers.append(ledger)
    if ledgers[0].get("sha256") != ledgers[1].get("sha256"):
        raise GateCSuiteError("Gate S replay ledgers are not byte-identical")
    audit = _strict(
        evidence.get("audit"),
        {"expected_row_count", "observed_row_count", "construction_certificate_count", "outcome_counts", "predicate_counts", "failure_code_counts", "internal_error_count", "certificate_disagreement_count", "complete_ledger", "request_result_binding", "forbidden_field_scan"},
        "gate_s_evidence.audit",
    )
    expected_predicates = {
        name: {"pass": 4096, "fail": 0, "not_evaluated": 0}
        for name in (
            "frozen_barrier",
            "non_capturable_barrier",
            "strict_exactly_two_components",
            "no_cross_component_entry",
        )
    }
    expected_audit = {
        "expected_row_count": 4096,
        "observed_row_count": 4096,
        "construction_certificate_count": 4096,
        "outcome_counts": {"pass": 4096, "fail": 0, "error": 0},
        "predicate_counts": expected_predicates,
        "failure_code_counts": [],
        "internal_error_count": 0,
        "certificate_disagreement_count": 0,
        "complete_ledger": True,
        "request_result_binding": True,
        "forbidden_field_scan": True,
    }
    if audit != expected_audit:
        raise GateCSuiteError("Gate S evidence does not record an exact 4096/4096 GO")


def project_internal(
    *, target_path: Path, board_stream_path: Path, catalog_path: Path,
    proposals_path: Path, certificates_path: Path
) -> None:
    target, _ = _load_json(target_path)
    boards, _ = _load_jsonl(board_stream_path)
    catalog, _ = _load_json(catalog_path, canonical=False)
    proposals = discovery.project_board_stream_to_proposals(target, boards)
    certificates = [
        discovery.construction_certificate_for_board_row(board, catalog)
        for board in boards
    ]
    proposals_path.parent.mkdir(parents=True, exist_ok=True)
    certificates_path.parent.mkdir(parents=True, exist_ok=True)
    proposals_path.write_bytes(discovery.canonical_jsonl_bytes(proposals))
    certificates_path.write_bytes(discovery.canonical_jsonl_bytes(certificates))


def _validate_ref(reference: dict[str, Any], root: Path, expected_schema: str) -> Path:
    path = _resolve_ref(reference.get("path"), root)
    if reference.get("schema_version") != expected_schema:
        raise GateCSuiteError(f"artifact schema mismatch: {path}")
    if reference.get("sha256") != sha256_hex(path.read_bytes()):
        raise GateCSuiteError(f"artifact hash mismatch: {path}")
    return path


def _expected_inventory(manifest: dict[str, Any], root: Path, suite_path: Path) -> None:
    output_root = root / "data/discovery/wave_69r/calibration/inputs"
    if suite_path.resolve() != (output_root / "suite-manifest.json").resolve():
        raise GateCSuiteError("suite manifest path is not deterministic")
    expected_root = {"suite-manifest.json"}
    expected_files = {
        "target_ref": "target.json",
        "board_stream_ref": "board-stream.jsonl",
        "construction_certificates_ref": "construction-certificates.jsonl",
        "proposals_ref": "proposals.jsonl",
        "generation_receipt_ref": "generation-receipt.json",
        "pool_manifest_ref": "pool-manifest.json",
        "policy_orders_ref": "policy-orders.json",
    }
    inodes: set[tuple[int, int]] = set()
    for entry in manifest["targets"]:
        digest = entry["target_id"].split(":", 1)[1]
        expected_root.add(digest)
        directory = output_root / digest
        if directory.is_symlink() or not directory.is_dir():
            raise GateCSuiteError("target artifact directory must be real")
        if {item.name for item in directory.iterdir()} != set(expected_files.values()):
            raise GateCSuiteError("target artifact inventory differs")
        for ref_name, filename in expected_files.items():
            path = directory / filename
            if entry[ref_name]["path"] != path.relative_to(root).as_posix():
                raise GateCSuiteError("target artifact path is not deterministic")
            if path.is_symlink() or not path.is_file():
                raise GateCSuiteError("target artifact must be a regular file")
            inode = (path.stat().st_dev, path.stat().st_ino)
            if inode in inodes:
                raise GateCSuiteError("target artifacts may not alias by hard link")
            inodes.add(inode)
    if {item.name for item in output_root.iterdir()} != expected_root:
        raise GateCSuiteError("Gate C input tree contains an unexpected artifact")


def validate_suite_manifest(
    manifest: dict[str, Any], *, root: Path, suite_path: Path,
    enforce_inventory: bool = True
) -> None:
    _strict(manifest, SUITE_KEYS, "suite")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise GateCSuiteError("suite schema mismatch")
    if manifest.get("suite_id") != suite_id_for(manifest):
        raise GateCSuiteError("suite identity mismatch")
    if manifest.get("phase") != "pre_verification_freeze":
        raise GateCSuiteError("suite phase mismatch")
    if manifest.get("target_count") != TARGET_COUNT or manifest.get("proposal_count_per_target") != POOL_SIZE:
        raise GateCSuiteError("suite cardinality mismatch")
    sources = _strict(
        manifest.get("source_repositories"),
        {"partizan", "astralbase", "bitmesh", "thermograph"},
        "suite.source_repositories",
    )
    if any(HEX40.fullmatch(str(value)) is None for value in sources.values()):
        raise GateCSuiteError("suite source commits must be immutable")
    if {name: sources[name] for name in PINNED_EXTERNAL_COMMITS} != PINNED_EXTERNAL_COMMITS:
        raise GateCSuiteError("suite external commits differ from preregistration")
    temporal = _strict(
        manifest.get("temporal_boundary"),
        {"implementation_commit", "implementation_parent", "gate_s_evidence_commit", "pre_result_parent_commit"},
        "suite.temporal_boundary",
    )
    if temporal.get("implementation_commit") != sources["partizan"] or temporal.get("implementation_parent") != IMPLEMENTATION_PARENT:
        raise GateCSuiteError("suite implementation ancestry mismatch")
    if temporal.get("gate_s_evidence_commit") != temporal.get("pre_result_parent_commit"):
        raise GateCSuiteError("Gate C pre-result parent must be Gate S evidence commit")
    seed_contract = manifest.get("seed_contract")
    if seed_contract != {
        "algorithm": "sha256_first_u64_big_endian_v1",
        "domain_hex": CALIBRATION_SEED_DOMAIN.hex(),
        "target_id_encoding": "ascii",
    }:
        raise GateCSuiteError("suite calibration seed contract mismatch")
    if manifest.get("policy_contract") != {
        "schema_version": POLICY_SCHEMA_VERSION,
        "random_replicates": RANDOM_REPLICATES,
        "random_seed_domain_hex": RANDOM_SEED_DOMAIN.hex(),
        "permutation_algorithm": "splitmix64_rejection_fisher_yates_v1",
        "heuristic_version": baselines.HEURISTIC_POLICY_VERSION,
    }:
        raise GateCSuiteError("suite policy contract mismatch")
    if manifest.get("freeze_boundary") != {
        "gate_s_go_required": True,
        "verifier_calls": 0,
        "results_artifacts_present": False,
        "stage_b_material_present": False,
        "wave70_material_present": False,
        "policy_orders_frozen_before_verification": True,
    }:
        raise GateCSuiteError("suite pre-result boundary mismatch")
    registry_ref = manifest.get("registry_ref")
    _strict(
        registry_ref,
        {"path", "schema_version", "registry_id", "sha256"},
        "suite.registry_ref",
    )
    registry_path = _validate_ref(registry_ref, root, "partizan.wave69_target_registry.v0.1")
    registry, registry_payload, stage_targets = load_exact_stage_a_targets(registry_path)
    if registry_ref.get("registry_id") != registry.get("registry_id") or registry_ref.get("sha256") != sha256_hex(registry_payload):
        raise GateCSuiteError("suite registry reference mismatch")
    prereg_ref = manifest.get("preregistration_ref")
    _strict(
        prereg_ref,
        {"path", "schema_version", "preregistration_id", "sha256"},
        "suite.preregistration_ref",
    )
    prereg_path = _validate_ref(prereg_ref, root, "text/markdown")
    prereg_payload = prereg_path.read_bytes()
    if prereg_ref.get("preregistration_id") != f"prereg-sha256:{sha256_hex(prereg_payload)}":
        raise GateCSuiteError("suite preregistration reference mismatch")
    implementation = _strict(
        manifest.get("implementation"),
        {"implementation_id", "partizan_commit", "components"},
        "suite.implementation",
    )
    if implementation.get("partizan_commit") != sources["partizan"] or implementation.get("implementation_id") != _identity("implementation", implementation, "implementation_id"):
        raise GateCSuiteError("suite implementation binding mismatch")
    components = implementation.get("components")
    expected_component_paths = list(IMPLEMENTATION_COMPONENT_PATHS)
    if (
        not isinstance(components, list)
        or [component.get("path") for component in components]
        != expected_component_paths
    ):
        raise GateCSuiteError("suite implementation component inventory mismatch")
    for component in components:
        _strict(component, {"path", "sha256"}, "suite.implementation.component")
        path = _resolve_ref(component.get("path"), root)
        if component.get("sha256") != sha256_hex(path.read_bytes()):
            raise GateCSuiteError("suite implementation component hash mismatch")
    gate_ref = manifest.get("gate_s_go_ref")
    _strict(
        gate_ref,
        {"path", "schema_version", "evidence_id", "evidence_commit", "decision", "sha256"},
        "suite.gate_s_go_ref",
    )
    gate_path = _validate_ref(gate_ref, root, GATE_S_EVIDENCE_SCHEMA_VERSION)
    gate_evidence, gate_payload = _load_json(gate_path)
    if gate_ref.get("evidence_id") != gate_evidence.get("evidence_id") or gate_ref.get("sha256") != sha256_hex(gate_payload) or gate_ref.get("decision") != "GO" or gate_ref.get("evidence_commit") != temporal["gate_s_evidence_commit"]:
        raise GateCSuiteError("suite Gate S reference mismatch")
    gate_relative = _repo_relative(gate_path, root)
    if _git(root, "show", f"{temporal['gate_s_evidence_commit']}:{gate_relative}") != gate_payload:
        raise GateCSuiteError("suite Gate S evidence bytes differ from E_s commit")
    try:
        gate_s.validate_evidence_manifest(
            gate_evidence,
            repository_root=root,
            require_git_binding=True,
        )
    except gate_s.GateSContractError as error:
        raise GateCSuiteError(f"suite Gate S evidence failed full revalidation: {error}") from error
    validate_gate_s_go(
        gate_evidence,
        implementation_commit=sources["partizan"],
        source_repositories=sources,
        evidence_commit=temporal["gate_s_evidence_commit"],
    )
    supply_commit = gate_evidence["supply_pre_result"]["commit"]
    if supply_commit == temporal["gate_s_evidence_commit"]:
        raise GateCSuiteError("Gate S input and evidence commits must be distinct")
    _require_direct_child(
        root,
        supply_commit,
        sources["partizan"],
        "Gate S pre-result P_s",
    )
    _require_direct_child(
        root,
        temporal["gate_s_evidence_commit"],
        supply_commit,
        "Gate S evidence E_s",
    )
    entries = manifest.get("targets")
    if not isinstance(entries, list) or [entry.get("target_id") for entry in entries] != list(EXPECTED_TARGET_IDS):
        raise GateCSuiteError("suite targets differ from immutable Stage A target set")
    target_by_id = {item["target_spec"]["target_id"]: item for item in stage_targets}
    for entry in entries:
        _strict(entry, TARGET_KEYS, "suite.target")
        item = target_by_id[entry["target_id"]]
        if entry["family"] != item["family"] or entry["bin_index"] != item["bin"]["index"] or entry["calibration_seed"] != calibration_seed(entry["target_id"]):
            raise GateCSuiteError("suite target metadata or calibration seed mismatch")
        expected_ref_keys = {
            "target_ref": {"path", "schema_version", "sha256", "target_id"},
            "board_stream_ref": {"path", "schema_version", "sha256", "row_count"},
            "construction_certificates_ref": {"path", "schema_version", "sha256", "row_count"},
            "proposals_ref": {"path", "schema_version", "sha256", "row_count"},
            "generation_receipt_ref": {"path", "schema_version", "sha256", "receipt_id"},
            "pool_manifest_ref": {"path", "schema_version", "sha256", "pool_id"},
            "policy_orders_ref": {"path", "schema_version", "sha256", "policy_orders_id"},
        }
        for ref_name, expected_keys in expected_ref_keys.items():
            _strict(entry[ref_name], expected_keys, f"suite.target.{ref_name}")
        for ref_name in (
            "board_stream_ref",
            "construction_certificates_ref",
            "proposals_ref",
        ):
            if entry[ref_name].get("row_count") != POOL_SIZE:
                raise GateCSuiteError(f"suite target {ref_name} row count mismatch")
        target_path = _validate_ref(entry["target_ref"], root, discovery.TARGET_SCHEMA_VERSION)
        boards_path = _validate_ref(entry["board_stream_ref"], root, discovery.BOARD_STREAM_SCHEMA_VERSION)
        certificates_path = _validate_ref(entry["construction_certificates_ref"], root, discovery.CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION)
        proposals_path = _validate_ref(entry["proposals_ref"], root, discovery.PROPOSAL_SCHEMA_VERSION)
        receipt_path = _validate_ref(entry["generation_receipt_ref"], root, discovery.GENERATION_RECEIPT_SCHEMA_VERSION_V2)
        pool_path = _validate_ref(entry["pool_manifest_ref"], root, discovery.POOL_SCHEMA_VERSION_V3)
        policy_path = _validate_ref(entry["policy_orders_ref"], root, POLICY_SCHEMA_VERSION)
        target, _ = _load_json(target_path)
        boards, _ = _load_jsonl(boards_path)
        certificates, _ = _load_jsonl(certificates_path)
        proposals, _ = _load_jsonl(proposals_path)
        receipt, _ = _load_json(receipt_path)
        pool, _ = _load_json(pool_path)
        policy, _ = _load_json(policy_path)
        if target != item["target_spec"] or len(boards) != POOL_SIZE or len(certificates) != POOL_SIZE or len(proposals) != POOL_SIZE:
            raise GateCSuiteError("suite target artifact cardinality or target mismatch")
        if entry["target_ref"].get("target_id") != entry["target_id"]:
            raise GateCSuiteError("suite target reference id mismatch")
        errors = discovery.validate_generation_receipt_v2(receipt, target, proposals, root)
        if errors:
            raise GateCSuiteError("suite receipt invalid: " + "; ".join(errors))
        errors = discovery.validate_candidate_pool_manifest_v3(pool, target, proposals, root)
        if errors:
            raise GateCSuiteError("suite pool invalid: " + "; ".join(errors))
        validate_policy_orders(policy, target, pool, proposals)
        for ref, key, expected in (
            (entry["generation_receipt_ref"], "receipt_id", receipt["receipt_id"]),
            (entry["pool_manifest_ref"], "pool_id", pool["pool_id"]),
            (entry["policy_orders_ref"], "policy_orders_id", policy["policy_orders_id"]),
        ):
            if ref.get(key) != expected:
                raise GateCSuiteError(f"suite target {key} reference mismatch")
    if suite_path.read_bytes() != canonical_bytes(manifest):
        raise GateCSuiteError("suite manifest bytes are not canonical")
    if enforce_inventory:
        _expected_inventory(manifest, root, suite_path)


CommandRunner = Callable[[Sequence[str], Path], None]


def _run(command: Sequence[str], cwd: Path) -> None:
    result = subprocess.run(
        tuple(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        raise GateCSuiteError(
            f"command failed ({' '.join(command)}): "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _implementation_boundary(root: Path, commit: str, paths: Iterable[Path]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "implementation_id": "implementation-sha256:" + "0" * 64,
        "partizan_commit": commit,
        "components": [
            {"path": _repo_relative(path, root), "sha256": sha256_hex(path.read_bytes())}
            for path in paths
        ],
    }
    value["implementation_id"] = _identity("implementation", value, "implementation_id")
    return value


def validate_committed_pre_result(
    *,
    root: Path,
    suite_path: Path,
    pre_result_commit: str,
    require_current_head: bool,
) -> dict[str, Any]:
    """Validate exact P_c bytes, optionally requiring the checkout itself at P_c."""

    repository = root.resolve(strict=True)
    suite_path = suite_path.resolve(strict=True)
    manifest, suite_payload = _load_json(suite_path)
    validate_suite_manifest(manifest, root=repository, suite_path=suite_path)
    if HEX40.fullmatch(pre_result_commit) is None:
        raise GateCSuiteError("Gate C pre-result P_c is not a full commit")
    if require_current_head:
        current = clean_commit(repository, "Gate C P_c repository")
        if current != pre_result_commit:
            raise GateCSuiteError("Gate C checkout is not the committed P_c")
    evidence_commit = manifest["temporal_boundary"]["pre_result_parent_commit"]
    _require_direct_child(
        repository,
        pre_result_commit,
        evidence_commit,
        "Gate C pre-result P_c",
    )
    suite_relative = _repo_relative(suite_path, repository)
    if _git(repository, "show", f"{pre_result_commit}:{suite_relative}") != suite_payload:
        raise GateCSuiteError("Gate C suite bytes are not committed at P_c")
    output_root = suite_path.parent
    input_paths = sorted(
        path.relative_to(repository).as_posix()
        for path in output_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    freeze_record = "docs/discovery_wave_69r_calibration_freeze.md"
    _require_exact_commit_inventory(
        repository,
        commit=pre_result_commit,
        expected_paths=[*input_paths, freeze_record],
        label="Gate C pre-result P_c",
    )
    return manifest


def check_only(*, root: Path, suite_path: Path) -> dict[str, Any]:
    repository = root.resolve(strict=True)
    pre_result_commit = clean_commit(repository, "Gate C P_c repository")
    return validate_committed_pre_result(
        root=repository,
        suite_path=suite_path,
        pre_result_commit=pre_result_commit,
        require_current_head=True,
    )


def _freeze_gate_c_suite_staged(
    *,
    artifact_root: Path,
    implementation_root: Path,
    registry_path: Path,
    preregistration_path: Path,
    gate_s_evidence_path: Path,
    output_root: Path,
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
    logical_output_root: Path,
    command_runner: CommandRunner = _run,
) -> dict[str, Any]:
    """Build P_c under a sibling staging root using final logical references."""

    artifact_root = artifact_root.resolve(strict=True)
    implementation_root = implementation_root.resolve(strict=True)
    output_root = output_root.resolve()
    logical_output_root = logical_output_root.resolve()
    if logical_output_root != artifact_root / "data/discovery/wave_69r/calibration/inputs":
        raise GateCSuiteError("Gate C output root is not deterministic")
    if output_root.exists() and any(output_root.iterdir()):
        raise GateCSuiteError("Gate C output root must be absent or empty")

    def logical_path(path: Path) -> Path:
        return logical_output_root / path.resolve().relative_to(output_root)

    pre_result_parent = clean_commit(artifact_root, "Gate C artifact repository")
    implementation_commit = clean_commit(implementation_root, "Partizan implementation")
    implementation_parent = _git(
        implementation_root, "rev-parse", "HEAD^"
    ).decode("ascii").strip()
    if implementation_parent != IMPLEMENTATION_PARENT:
        raise GateCSuiteError("implementation I is not a direct child of Wave 69 evidence E")
    if pre_result_parent == implementation_commit:
        raise GateCSuiteError("Gate C requires a committed Gate S evidence parent after I")
    _git(
        artifact_root,
        "merge-base",
        "--is-ancestor",
        implementation_commit,
        pre_result_parent,
    )
    source_repositories = {
        "partizan": implementation_commit,
        "astralbase": clean_commit(astralbase_dir, "astralbase"),
        "bitmesh": clean_commit(bitmesh_dir, "bitmesh"),
        "thermograph": clean_commit(thermograph_dir, "thermograph"),
    }
    if {name: source_repositories[name] for name in PINNED_EXTERNAL_COMMITS} != PINNED_EXTERNAL_COMMITS:
        raise GateCSuiteError("external repositories differ from preregistered commits")

    implementation_paths = tuple(
        artifact_root / path for path in IMPLEMENTATION_COMPONENT_PATHS
    )
    for path in implementation_paths:
        relative = _repo_relative(path, artifact_root)
        committed = _git(implementation_root, "show", f"{implementation_commit}:{relative}")
        if committed != path.read_bytes():
            raise GateCSuiteError(f"implementation component differs from I: {relative}")

    registry, registry_payload, stage_targets = load_exact_stage_a_targets(registry_path)
    prereg_payload = preregistration_path.read_bytes()
    gate_evidence, gate_payload = _load_json(gate_s_evidence_path)
    try:
        gate_s.validate_evidence_manifest(
            gate_evidence,
            repository_root=artifact_root,
            require_git_binding=True,
        )
    except gate_s.GateSContractError as error:
        raise GateCSuiteError(f"Gate S evidence failed full revalidation: {error}") from error
    validate_gate_s_go(
        gate_evidence,
        implementation_commit=implementation_commit,
        source_repositories=source_repositories,
        evidence_commit=pre_result_parent,
    )
    _require_direct_child(
        artifact_root,
        gate_evidence["supply_pre_result"]["commit"],
        implementation_commit,
        "Gate S pre-result P_s",
    )
    _require_direct_child(
        artifact_root,
        pre_result_parent,
        gate_evidence["supply_pre_result"]["commit"],
        "Gate S evidence E_s",
    )

    catalog_path = artifact_root / "docs/discovery_wave_69r_construction_catalog.v0.2.json"
    catalog, catalog_payload = _load_json(catalog_path, canonical=False)
    catalog_errors = discovery.validate_construction_catalog(catalog)
    if catalog_errors:
        raise GateCSuiteError("construction catalog invalid: " + "; ".join(catalog_errors))
    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for registry_item in stage_targets:
        target = registry_item["target_spec"]
        target_id = target["target_id"]
        directory = output_root / target_id.split(":", 1)[1]
        directory.mkdir(parents=True, exist_ok=False)
        target_path = directory / "target.json"
        boards_path = directory / "board-stream.jsonl"
        certificates_path = directory / "construction-certificates.jsonl"
        proposals_path = directory / "proposals.jsonl"
        receipt_path = directory / "generation-receipt.json"
        pool_path = directory / "pool-manifest.json"
        policy_path = directory / "policy-orders.json"
        _write(target_path, canonical_bytes(target))
        seed = calibration_seed(target_id)

        with tempfile.TemporaryDirectory(prefix="partizan-wave69r-gate-c-") as temp_dir:
            temp = Path(temp_dir)
            board_report_path = temp / "board-determinism.json"
            command_runner(
                (
                    sys.executable,
                    str(implementation_root / "engine/orchestrator.py"),
                    "discovery-generate-board-stream-v2",
                    "--output",
                    str(boards_path),
                    "--determinism-report",
                    str(board_report_path),
                    "--pool-size",
                    str(POOL_SIZE),
                    "--random-seed",
                    str(seed),
                ),
                implementation_root,
            )
            boards, board_payload = _load_jsonl(boards_path)
            board_report, _ = _load_json(board_report_path)
            board_sha = sha256_hex(board_payload)
            if board_report != {
                "schema_version": "partizan.candidate_board_stream_generation.v0.1",
                "artifact_sha256": board_sha,
                "row_count": POOL_SIZE,
                "generator": {
                    key: boards[0]["generator"][key]
                    for key in ("name", "version", "code_commit", "config_sha256", "random_seed")
                },
                "executions": {
                    "mode": "separate_python_processes_v1",
                    "run_count": 2,
                    "raw_artifact_sha256": [board_sha, board_sha],
                    "byte_identical": True,
                },
                "target_fields_consumed": [],
            }:
                raise GateCSuiteError("board generator determinism report mismatch")
            proposal_runs = [temp / "proposals-0.jsonl", temp / "proposals-1.jsonl"]
            certificate_runs = [temp / "certificates-0.jsonl", temp / "certificates-1.jsonl"]
            for proposal_run, certificate_run in zip(proposal_runs, certificate_runs):
                command_runner(
                    (
                        sys.executable,
                        str(implementation_root / "scripts/freeze_wave69r_gate_c_suite.py"),
                        "project-internal",
                        "--target",
                        str(target_path),
                        "--board-stream",
                        str(boards_path),
                        "--catalog",
                        str(catalog_path),
                        "--proposals",
                        str(proposal_run),
                        "--certificates",
                        str(certificate_run),
                    ),
                    implementation_root,
                )
            proposal_payloads = [path.read_bytes() for path in proposal_runs]
            certificate_payloads = [path.read_bytes() for path in certificate_runs]
            if len(set(proposal_payloads)) != 1 or len(set(certificate_payloads)) != 1:
                raise GateCSuiteError("projection or certificate processes differ")
            _write(proposals_path, proposal_payloads[0])
            _write(certificates_path, certificate_payloads[0])

        proposals, proposal_payload = _load_jsonl(proposals_path)
        certificates, certificate_payload = _load_jsonl(certificates_path)
        if len(boards) != POOL_SIZE or len(proposals) != POOL_SIZE or len(certificates) != POOL_SIZE:
            raise GateCSuiteError("Gate C target artifacts must each contain 1024 rows")
        proposal_sha = sha256_hex(proposal_payload)
        certificate_sha = sha256_hex(certificate_payload)
        receipt = discovery.build_generation_receipt_v2(
            target_path=_repo_relative(logical_path(target_path), artifact_root),
            target_spec=target,
            board_stream_path=_repo_relative(logical_path(boards_path), artifact_root),
            board_rows=boards,
            construction_catalog_path=_repo_relative(catalog_path, artifact_root),
            construction_catalog=catalog,
            construction_catalog_sha256=sha256_hex(catalog_payload),
            construction_certificates_path=_repo_relative(logical_path(certificates_path), artifact_root),
            construction_certificates=certificates,
            candidate_artifact_path=_repo_relative(logical_path(proposals_path), artifact_root),
            proposals=proposals,
            board_stream_process_sha256=[board_sha, board_sha],
            construction_certificate_process_sha256=[certificate_sha, certificate_sha],
            projection_process_sha256=[proposal_sha, proposal_sha],
            source_repositories=source_repositories,
        )
        _write(receipt_path, canonical_bytes(receipt))
        pool = discovery.build_candidate_pool_manifest_v3(
            generation_receipt=receipt,
            generation_receipt_path=_repo_relative(logical_path(receipt_path), artifact_root),
        )
        _write(pool_path, canonical_bytes(pool))
        policy = build_policy_orders(target, pool, proposals)
        validate_policy_orders(policy, target, pool, proposals)
        _write(policy_path, canonical_bytes(policy))
        entries.append(
            {
                "target_id": target_id,
                "family": registry_item["family"],
                "bin_index": registry_item["bin"]["index"],
                "calibration_seed": seed,
                "target_ref": _artifact_ref(target_path, artifact_root, schema_version=discovery.TARGET_SCHEMA_VERSION, id_key="target_id", identifier=target_id, reference_path=logical_path(target_path)),
                "board_stream_ref": _artifact_ref(boards_path, artifact_root, schema_version=discovery.BOARD_STREAM_SCHEMA_VERSION, row_count=POOL_SIZE, reference_path=logical_path(boards_path)),
                "construction_certificates_ref": _artifact_ref(certificates_path, artifact_root, schema_version=discovery.CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION, row_count=POOL_SIZE, reference_path=logical_path(certificates_path)),
                "proposals_ref": _artifact_ref(proposals_path, artifact_root, schema_version=discovery.PROPOSAL_SCHEMA_VERSION, row_count=POOL_SIZE, reference_path=logical_path(proposals_path)),
                "generation_receipt_ref": _artifact_ref(receipt_path, artifact_root, schema_version=discovery.GENERATION_RECEIPT_SCHEMA_VERSION_V2, id_key="receipt_id", identifier=receipt["receipt_id"], reference_path=logical_path(receipt_path)),
                "pool_manifest_ref": _artifact_ref(pool_path, artifact_root, schema_version=discovery.POOL_SCHEMA_VERSION_V3, id_key="pool_id", identifier=pool["pool_id"], reference_path=logical_path(pool_path)),
                "policy_orders_ref": _artifact_ref(policy_path, artifact_root, schema_version=POLICY_SCHEMA_VERSION, id_key="policy_orders_id", identifier=policy["policy_orders_id"], reference_path=logical_path(policy_path)),
            }
        )

    implementation = _implementation_boundary(
        artifact_root, implementation_commit, implementation_paths
    )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": "suite-sha256:" + "0" * 64,
        "phase": "pre_verification_freeze",
        "registry_ref": {
            "path": _repo_relative(registry_path, artifact_root),
            "schema_version": "partizan.wave69_target_registry.v0.1",
            "registry_id": registry["registry_id"],
            "sha256": sha256_hex(registry_payload),
        },
        "preregistration_ref": {
            "path": _repo_relative(preregistration_path, artifact_root),
            "schema_version": "text/markdown",
            "preregistration_id": f"prereg-sha256:{sha256_hex(prereg_payload)}",
            "sha256": sha256_hex(prereg_payload),
        },
        "gate_s_go_ref": {
            "path": _repo_relative(gate_s_evidence_path, artifact_root),
            "schema_version": GATE_S_EVIDENCE_SCHEMA_VERSION,
            "evidence_id": gate_evidence["evidence_id"],
            "evidence_commit": pre_result_parent,
            "decision": "GO",
            "sha256": sha256_hex(gate_payload),
        },
        "implementation": implementation,
        "temporal_boundary": {
            "implementation_commit": implementation_commit,
            "implementation_parent": IMPLEMENTATION_PARENT,
            "gate_s_evidence_commit": pre_result_parent,
            "pre_result_parent_commit": pre_result_parent,
        },
        "source_repositories": source_repositories,
        "seed_contract": {
            "algorithm": "sha256_first_u64_big_endian_v1",
            "domain_hex": CALIBRATION_SEED_DOMAIN.hex(),
            "target_id_encoding": "ascii",
        },
        "policy_contract": {
            "schema_version": POLICY_SCHEMA_VERSION,
            "random_replicates": RANDOM_REPLICATES,
            "random_seed_domain_hex": RANDOM_SEED_DOMAIN.hex(),
            "permutation_algorithm": "splitmix64_rejection_fisher_yates_v1",
            "heuristic_version": baselines.HEURISTIC_POLICY_VERSION,
        },
        "target_count": TARGET_COUNT,
        "proposal_count_per_target": POOL_SIZE,
        "targets": entries,
        "freeze_boundary": {
            "gate_s_go_required": True,
            "verifier_calls": 0,
            "results_artifacts_present": False,
            "stage_b_material_present": False,
            "wave70_material_present": False,
            "policy_orders_frozen_before_verification": True,
        },
    }
    manifest["suite_id"] = suite_id_for(manifest)
    suite_path = output_root / "suite-manifest.json"
    _write(suite_path, canonical_bytes(manifest))
    return manifest


def freeze_gate_c_suite(
    *,
    artifact_root: Path,
    implementation_root: Path,
    registry_path: Path,
    preregistration_path: Path,
    gate_s_evidence_path: Path,
    output_root: Path,
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
    command_runner: CommandRunner = _run,
) -> dict[str, Any]:
    """Atomically create P_c after a separately committed E_s GO."""

    artifacts = artifact_root.resolve(strict=True)
    final_root = output_root.resolve()
    expected = artifacts / "data/discovery/wave_69r/calibration/inputs"
    if final_root != expected:
        raise GateCSuiteError("Gate C output root is not deterministic")
    if final_root.exists():
        raise GateCSuiteError("Gate C output root already exists; replacement is forbidden")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix="wave69r-gate-c-freeze-", dir=final_root.parent)
    )
    moved = False
    try:
        manifest = _freeze_gate_c_suite_staged(
            artifact_root=artifacts,
            implementation_root=implementation_root,
            registry_path=registry_path,
            preregistration_path=preregistration_path,
            gate_s_evidence_path=gate_s_evidence_path,
            output_root=staging,
            logical_output_root=final_root,
            astralbase_dir=astralbase_dir,
            bitmesh_dir=bitmesh_dir,
            thermograph_dir=thermograph_dir,
            command_runner=command_runner,
        )
        os.replace(staging, final_root)
        moved = True
        suite_path = final_root / "suite-manifest.json"
        validate_suite_manifest(manifest, root=artifacts, suite_path=suite_path)
        return manifest
    except Exception:
        shutil.rmtree(final_root if moved else staging, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    internal = commands.add_parser("project-internal", help=argparse.SUPPRESS)
    internal.add_argument("--target", type=Path, required=True)
    internal.add_argument("--board-stream", type=Path, required=True)
    internal.add_argument("--catalog", type=Path, required=True)
    internal.add_argument("--proposals", type=Path, required=True)
    internal.add_argument("--certificates", type=Path, required=True)
    check = commands.add_parser("check-only")
    check.add_argument("--root", type=Path, default=ROOT)
    check.add_argument("--suite", type=Path, required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--artifact-root", type=Path, default=ROOT)
    freeze.add_argument("--implementation-root", type=Path, required=True)
    freeze.add_argument("--registry", type=Path)
    freeze.add_argument("--preregistration", type=Path)
    freeze.add_argument("--gate-s-evidence", type=Path, required=True)
    freeze.add_argument("--output-root", type=Path)
    freeze.add_argument("--astralbase-dir", type=Path, required=True)
    freeze.add_argument("--bitmesh-dir", type=Path, required=True)
    freeze.add_argument("--thermograph-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "project-internal":
        project_internal(
            target_path=args.target,
            board_stream_path=args.board_stream,
            catalog_path=args.catalog,
            proposals_path=args.proposals,
            certificates_path=args.certificates,
        )
        return 0
    if args.command == "freeze":
        artifact_root = args.artifact_root.resolve()
        manifest = freeze_gate_c_suite(
            artifact_root=artifact_root,
            implementation_root=args.implementation_root,
            registry_path=args.registry or artifact_root / DEFAULT_REGISTRY.relative_to(ROOT),
            preregistration_path=(
                args.preregistration
                or artifact_root / DEFAULT_PREREGISTRATION.relative_to(ROOT)
            ),
            gate_s_evidence_path=args.gate_s_evidence,
            output_root=args.output_root or artifact_root / DEFAULT_OUTPUT_ROOT.relative_to(ROOT),
            astralbase_dir=args.astralbase_dir,
            bitmesh_dir=args.bitmesh_dir,
            thermograph_dir=args.thermograph_dir,
        )
        print(f"wave69r Gate C suite frozen: {manifest['suite_id']}")
        return 0
    manifest = check_only(root=args.root, suite_path=args.suite)
    print(f"wave69r Gate C suite: ok ({manifest['suite_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
