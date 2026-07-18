#!/usr/bin/env python3
"""Freeze the preregistered Wave 69 Stage A suite before verification.

This command can generate candidates, freeze Candidate Pool v0.2 manifests,
and freeze random/heuristic policy orders.  It deliberately has no verifier or
result interface.  ``--check-only`` only reads and validates existing files.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_PATH = ROOT / "python" / "partizan" / "discovery.py"
DEFAULT_REGISTRY = (
    ROOT / "docs/discovery_targets/wave_69_target_registry.v0.1.json"
)
DEFAULT_PREREGISTRATION = ROOT / "docs/discovery_wave_69_preregistration.md"
DEFAULT_OUTPUT_ROOT = ROOT / "data/discovery/wave_69/stage_a"
DEFAULT_POOL_ORCHESTRATOR = ROOT / "engine/orchestrator.py"
DEFAULT_BASELINE_ORCHESTRATOR = ROOT / "scripts/wave69_discovery_baselines.py"
DEFAULT_ASTRALBASE = ROOT.parent / "astralbase"
DEFAULT_BITMESH = ROOT.parent / "bitmesh"
DEFAULT_THERMOGRAPH = ROOT.parent / "thermograph"

SCHEMA_VERSION = "partizan.wave69_stage_suite.v0.1"
POLICY_ORDERS_SCHEMA_VERSION = "partizan.policy_orders.v0.1"
STAGE = "stage_a"
TARGET_COUNT = 6
POOL_SIZE = 1024
RANDOM_REPLICATES = 1000
SEED_DOMAIN = b"partizan/w69/pool/v1\0"
RESULTS_FILENAME = "verifier-results.jsonl"
BASELINE_REPORT_FILENAME = "baseline-report.json"
BASELINE_SUITE_INPUT_FILENAME = "baseline-suite-input.json"
BASELINE_SUITE_REPORT_FILENAME = "baseline-suite-report.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

SUITE_KEYS = {
    "schema_version",
    "suite_id",
    "stage",
    "phase",
    "registry_ref",
    "preregistration_ref",
    "implementation",
    "source_repositories",
    "seed_contract",
    "target_count",
    "proposal_count_per_target",
    "targets",
    "freeze_boundary",
}
TARGET_ENTRY_KEYS = {
    "target_id",
    "family",
    "bin_index",
    "seed",
    "target_ref",
    "proposals_ref",
    "generation_receipt_ref",
    "pool_manifest_ref",
    "policy_orders_ref",
}


class SuiteFreezeError(ValueError):
    """Raised when the Stage A freeze contract cannot be satisfied."""


def _load_discovery_contract() -> Any:
    spec = importlib.util.spec_from_file_location(
        "partizan_wave69_suite_discovery", DISCOVERY_PATH
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


def _canonical_id(prefix: str, value: dict[str, Any], id_key: str) -> str:
    payload = {key: item for key, item in value.items() if key != id_key}
    return f"{prefix}-sha256:{sha256_hex(_canonical_bytes(payload))}"


def stage_seed(target_id: str, stage: str = STAGE) -> int:
    """Return the preregistered unsigned first-64-bit target seed."""

    if re.fullmatch(r"target-sha256:[0-9a-f]{64}", target_id) is None:
        raise SuiteFreezeError(f"invalid target id for seed derivation: {target_id}")
    digest = hashlib.sha256(
        SEED_DOMAIN + stage.encode("utf-8") + b"\0" + target_id.encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _strict_keys(value: Any, expected: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SuiteFreezeError(f"{path}: expected an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SuiteFreezeError(
            f"{path}: keys differ; missing={missing}, extra={extra}"
        )
    return value


def _repo_relative(path: Path, root: Path) -> str:
    resolved_root = root.resolve(strict=True)
    try:
        relative = path.resolve().relative_to(resolved_root)
    except ValueError as error:
        raise SuiteFreezeError(f"artifact is outside repository root: {path}") from error
    if not relative.parts:
        raise SuiteFreezeError("artifact path cannot be the repository root")
    return PurePosixPath(*relative.parts).as_posix()


def _resolve_bound_path(path: str, root: Path) -> Path:
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise SuiteFreezeError(f"invalid repository-relative path: {path!r}")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / Path(*PurePosixPath(path).parts)).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise SuiteFreezeError(f"artifact escapes repository root: {path}") from error
    return resolved


def _load_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SuiteFreezeError(f"cannot load JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise SuiteFreezeError(f"{path}: expected a JSON object")
    if raw != _canonical_bytes(value):
        raise SuiteFreezeError(f"{path}: bytes are not canonical JSON")
    return value, raw


def _load_canonical_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
        values = [json.loads(line) for line in raw.splitlines() if line]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SuiteFreezeError(f"cannot load JSONL artifact {path}: {error}") from error
    if not all(isinstance(value, dict) for value in values):
        raise SuiteFreezeError(f"{path}: every JSONL row must be an object")
    if raw != discovery.canonical_jsonl_bytes(values):
        raise SuiteFreezeError(f"{path}: bytes are not canonical JSONL")
    return values, raw


def _run_git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SuiteFreezeError(f"git {' '.join(arguments)} failed in {repo}: {detail}")
    return result.stdout


def _clean_commit(repo: Path, name: str) -> str:
    commit = _run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if HEX40.fullmatch(commit) is None:
        raise SuiteFreezeError(f"{name}: git HEAD is not a 40-character commit")
    dirty = _run_git(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise SuiteFreezeError(f"{name}: repository must be clean before suite freeze")
    return commit


def _require_committed_bytes(repo: Path, path: Path, commit: str) -> None:
    relative = _repo_relative(path, repo)
    committed = _run_git(repo, "show", f"{commit}:{relative}")
    try:
        working = path.read_bytes()
    except OSError as error:
        raise SuiteFreezeError(f"required committed input is missing: {path}") from error
    if committed != working:
        raise SuiteFreezeError(f"{relative}: working bytes differ from {commit}")


def _artifact_ref(
    path: Path,
    root: Path,
    *,
    schema_version: str,
    identifier_key: str | None = None,
    identifier: str | None = None,
    row_count: int | None = None,
) -> dict[str, Any]:
    raw = path.read_bytes()
    reference: dict[str, Any] = {
        "path": _repo_relative(path, root),
        "schema_version": schema_version,
        "sha256": sha256_hex(raw),
    }
    if identifier_key is not None:
        reference[identifier_key] = identifier
    if row_count is not None:
        reference["row_count"] = row_count
    return reference


def load_stage_a_targets(registry_path: Path) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    registry, raw = _load_canonical_json(registry_path)
    if registry.get("schema_version") != "partizan.wave69_target_registry.v0.1":
        raise SuiteFreezeError("registry: unsupported schema version")
    expected_id = _canonical_id("registry", registry, "registry_id")
    if registry.get("registry_id") != expected_id:
        raise SuiteFreezeError("registry: registry_id does not bind canonical bytes")
    targets = [item for item in registry.get("targets", []) if item.get("stage") == STAGE]
    if len(targets) != TARGET_COUNT:
        raise SuiteFreezeError(
            f"registry: expected exactly {TARGET_COUNT} Stage A targets, got {len(targets)}"
        )
    if any(item.get("stage") != STAGE for item in targets):
        raise SuiteFreezeError("registry: non-Stage-A target entered Stage A selection")
    target_ids = [item.get("target_spec", {}).get("target_id") for item in targets]
    if len(set(target_ids)) != TARGET_COUNT:
        raise SuiteFreezeError("registry: Stage A target ids must be unique")
    families = Counter(str(item.get("family")) for item in targets)
    if sorted(families.values()) != [2, 2, 2]:
        raise SuiteFreezeError("registry: Stage A requires two targets per family")
    for index, item in enumerate(targets):
        if item.get("bin", {}).get("index") not in {0, 3}:
            raise SuiteFreezeError(f"registry Stage A target[{index}] has wrong bin")
        errors = discovery.validate_target_spec(item.get("target_spec"))
        if errors:
            raise SuiteFreezeError(
                f"registry Stage A target[{index}] invalid: {'; '.join(errors)}"
            )
    return registry, raw, targets


def _load_baseline_contract(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "partizan_wave69_suite_baselines", path
    )
    if spec is None or spec.loader is None:
        raise SuiteFreezeError(f"cannot load baseline contract from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = getattr(module, "baselines", module)
    validator = getattr(contract, "validate_policy_orders", None)
    if not callable(validator):
        raise SuiteFreezeError("baseline module has no validate_policy_orders API")
    return contract


def _validate_exact_pre_result_tree(
    manifest: dict[str, Any], *, root: Path, suite_path: Path
) -> None:
    """Require the pre-result tree to contain only its 31 bound artifacts."""

    output_root = root / "data/discovery/wave_69/stage_a"
    expected_suite_path = output_root / "suite-manifest.json"
    if suite_path.absolute() != expected_suite_path:
        raise SuiteFreezeError("suite manifest must use the deterministic Stage A path")
    if output_root.is_symlink() or not output_root.is_dir():
        raise SuiteFreezeError("Stage A output root must be a real directory")
    if suite_path.is_symlink() or not suite_path.is_file():
        raise SuiteFreezeError("suite manifest must be a regular non-symlink file")

    expected_root_names = {"suite-manifest.json"}
    expected_inodes: set[tuple[int, int]] = set()
    for entry in manifest.get("targets", []):
        target_id = str(entry.get("target_id"))
        if re.fullmatch(r"target-sha256:[0-9a-f]{64}", target_id) is None:
            raise SuiteFreezeError("suite inventory contains an invalid target id")
        digest = target_id.split(":", 1)[1]
        expected_root_names.add(digest)
        target_dir = output_root / digest
        if target_dir.is_symlink() or not target_dir.is_dir():
            raise SuiteFreezeError(
                f"Stage A target directory must be real and non-symlink: {digest}"
            )
        expected_files = {
            "target_ref": "target.json",
            "proposals_ref": "proposals.jsonl",
            "generation_receipt_ref": "generation-receipt.json",
            "pool_manifest_ref": "pool-manifest.json",
            "policy_orders_ref": "policy-orders.json",
        }
        if {child.name for child in target_dir.iterdir()} != set(
            expected_files.values()
        ):
            raise SuiteFreezeError(
                f"Stage A target directory has an unexpected inventory: {digest}"
            )
        for ref_name, filename in expected_files.items():
            artifact = target_dir / filename
            reference = entry.get(ref_name)
            expected_relative = artifact.relative_to(root).as_posix()
            if not isinstance(reference, dict) or reference.get("path") != expected_relative:
                raise SuiteFreezeError(
                    f"suite target {target_id}: {ref_name} path is not deterministic"
                )
            if artifact.is_symlink() or not artifact.is_file():
                raise SuiteFreezeError(
                    f"Stage A artifact must be regular and non-symlink: {artifact}"
                )
            stat_result = artifact.stat()
            inode = (stat_result.st_dev, stat_result.st_ino)
            if inode in expected_inodes:
                raise SuiteFreezeError("Stage A artifacts must not be hard-link aliases")
            expected_inodes.add(inode)

    if {child.name for child in output_root.iterdir()} != expected_root_names:
        raise SuiteFreezeError("Stage A root has an unexpected file or directory")
    suite_stat = suite_path.stat()
    suite_inode = (suite_stat.st_dev, suite_stat.st_ino)
    if suite_inode in expected_inodes:
        raise SuiteFreezeError("suite manifest must not alias a target artifact")


def _policy_orders_projection(
    policy_orders: dict[str, Any],
    *,
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    proposals_path: Path,
    root: Path,
    baseline_contract: Any,
) -> dict[str, Any]:
    """Validate and return the policy commitment projection bound by the suite."""

    errors = baseline_contract.validate_policy_orders(
        policy_orders,
        target,
        pool,
        proposals,
        proposals_path=proposals_path,
        repository_root=root,
    )
    if errors:
        raise SuiteFreezeError(f"policy orders invalid: {'; '.join(errors)}")
    if policy_orders.get("schema_version") != POLICY_ORDERS_SCHEMA_VERSION:
        raise SuiteFreezeError("policy orders: unsupported schema version")
    policy_id = policy_orders.get("policy_orders_id")
    if re.fullmatch(r"policy-orders-sha256:[0-9a-f]{64}", str(policy_id)) is None:
        raise SuiteFreezeError("policy orders: invalid policy_orders_id")
    if policy_orders.get("target_id") != target.get("target_id"):
        raise SuiteFreezeError("policy orders: target id mismatch")
    if policy_orders.get("pool_id") != pool.get("pool_id"):
        raise SuiteFreezeError("policy orders: pool id mismatch")
    if policy_orders.get("freeze_boundary") != "before_any_verifier_result":
        raise SuiteFreezeError("policy orders: invalid freeze boundary")
    random_policy = policy_orders.get("random_policy")
    if not isinstance(random_policy, dict):
        raise SuiteFreezeError("policy orders: random_policy must be an object")
    if random_policy.get("replicate_count") != RANDOM_REPLICATES:
        raise SuiteFreezeError(
            f"policy orders: expected {RANDOM_REPLICATES} random commitments"
        )
    orders = random_policy.get("orders")
    if not isinstance(orders, list) or len(orders) != RANDOM_REPLICATES:
        raise SuiteFreezeError("policy orders: random order count mismatch")
    heuristic = policy_orders.get("heuristic_policy")
    if not isinstance(heuristic, dict) or not isinstance(
        heuristic.get("order"), dict
    ):
        raise SuiteFreezeError("policy orders: missing heuristic commitment")
    return {"policy_orders_id": policy_id, "schema_version": policy_orders["schema_version"]}


def _validate_target_artifacts(
    *,
    root: Path,
    registry_item: dict[str, Any],
    suite_entry: dict[str, Any],
    source_repositories: dict[str, str],
    baseline_contract: Any,
) -> None:
    _strict_keys(suite_entry, TARGET_ENTRY_KEYS, "suite target entry")
    target_spec = registry_item["target_spec"]
    target_id = target_spec["target_id"]
    if suite_entry["target_id"] != target_id:
        raise SuiteFreezeError("suite target entry: target_id differs from registry")
    if suite_entry["family"] != registry_item["family"]:
        raise SuiteFreezeError("suite target entry: family differs from registry")
    if suite_entry["bin_index"] != registry_item["bin"]["index"]:
        raise SuiteFreezeError("suite target entry: bin differs from registry")
    if suite_entry["seed"] != stage_seed(target_id):
        raise SuiteFreezeError("suite target entry: seed differs from preregistration")

    refs = {
        name: suite_entry[name]
        for name in (
            "target_ref",
            "proposals_ref",
            "generation_receipt_ref",
            "pool_manifest_ref",
            "policy_orders_ref",
        )
    }
    expected_ref_keys = {
        "target_ref": {"path", "schema_version", "sha256", "target_id"},
        "proposals_ref": {"path", "schema_version", "sha256", "row_count"},
        "generation_receipt_ref": {
            "path",
            "schema_version",
            "sha256",
            "receipt_id",
        },
        "pool_manifest_ref": {"path", "schema_version", "sha256", "pool_id"},
        "policy_orders_ref": {
            "path",
            "schema_version",
            "sha256",
            "policy_orders_id",
        },
    }
    paths: dict[str, Path] = {}
    for name, reference in refs.items():
        _strict_keys(reference, expected_ref_keys[name], f"suite target entry.{name}")
        path = _resolve_bound_path(reference.get("path"), root)
        relative = _repo_relative(path, root)
        if not relative.startswith("data/discovery/wave_69/stage_a/"):
            raise SuiteFreezeError(
                f"suite target entry: {name} is outside the Stage A tree"
            )
        paths[name] = path
        try:
            actual_hash = sha256_hex(path.read_bytes())
        except OSError as error:
            raise SuiteFreezeError(f"suite target entry: missing {name}: {path}") from error
        if reference.get("sha256") != actual_hash:
            raise SuiteFreezeError(f"suite target entry: {name} hash mismatch")

    target, _ = _load_canonical_json(paths["target_ref"])
    if target != target_spec:
        raise SuiteFreezeError("target artifact differs from committed registry target")
    if refs["target_ref"].get("target_id") != target_id:
        raise SuiteFreezeError("target reference id mismatch")
    if refs["target_ref"].get("schema_version") != discovery.TARGET_SCHEMA_VERSION:
        raise SuiteFreezeError("target reference schema mismatch")
    proposals, _ = _load_canonical_jsonl(paths["proposals_ref"])
    if len(proposals) != POOL_SIZE:
        raise SuiteFreezeError(f"proposal artifact must contain exactly {POOL_SIZE} rows")
    if refs["proposals_ref"].get("row_count") != POOL_SIZE:
        raise SuiteFreezeError("proposal reference row count mismatch")
    if refs["proposals_ref"].get("schema_version") != discovery.PROPOSAL_SCHEMA_VERSION:
        raise SuiteFreezeError("proposal reference schema mismatch")
    for index, proposal in enumerate(proposals):
        errors = discovery.validate_candidate_proposal(proposal, target)
        if errors:
            raise SuiteFreezeError(f"proposal[{index}] invalid: {'; '.join(errors)}")
    if len({row["candidate_key"] for row in proposals}) != POOL_SIZE:
        raise SuiteFreezeError("proposal artifact contains duplicate candidate keys")
    if len({row["position"]["symmetry_sha256"] for row in proposals}) != POOL_SIZE:
        raise SuiteFreezeError("proposal artifact contains duplicate symmetry orbits")

    receipt, _ = _load_canonical_json(paths["generation_receipt_ref"])
    receipt_errors = discovery.validate_generation_receipt(receipt, target, proposals)
    if receipt_errors:
        raise SuiteFreezeError(f"generation receipt invalid: {'; '.join(receipt_errors)}")
    if receipt.get("receipt_id") != refs["generation_receipt_ref"].get("receipt_id"):
        raise SuiteFreezeError("generation receipt reference id mismatch")
    if (
        refs["generation_receipt_ref"].get("schema_version")
        != discovery.GENERATION_RECEIPT_SCHEMA_VERSION
    ):
        raise SuiteFreezeError("generation receipt reference schema mismatch")
    executions = receipt.get("executions", {})
    if executions.get("mode") != "separate_python_processes_v1":
        raise SuiteFreezeError("receipt does not attest separate-process generation")
    if executions.get("run_count") != 2 or executions.get("byte_identical") is not True:
        raise SuiteFreezeError("receipt does not attest two byte-identical runs")

    pool, _ = _load_canonical_json(paths["pool_manifest_ref"])
    pool_errors = discovery.validate_candidate_pool_manifest(
        pool,
        target,
        proposals,
        paths["proposals_ref"],
        repository_root=root,
    )
    if pool_errors:
        raise SuiteFreezeError(f"pool manifest invalid: {'; '.join(pool_errors)}")
    if pool.get("schema_version") != discovery.POOL_SCHEMA_VERSION_V2:
        raise SuiteFreezeError("Stage A requires Candidate Pool manifest v0.2")
    if pool.get("pool_id") != refs["pool_manifest_ref"].get("pool_id"):
        raise SuiteFreezeError("pool manifest reference id mismatch")
    if refs["pool_manifest_ref"].get("schema_version") != discovery.POOL_SCHEMA_VERSION_V2:
        raise SuiteFreezeError("pool manifest reference schema mismatch")
    if pool.get("source_repositories") != source_repositories:
        raise SuiteFreezeError("pool source repositories differ from suite boundary")

    policy_orders, _ = _load_canonical_json(paths["policy_orders_ref"])
    projection = _policy_orders_projection(
        policy_orders,
        target=target,
        pool=pool,
        proposals=proposals,
        proposals_path=paths["proposals_ref"],
        root=root,
        baseline_contract=baseline_contract,
    )
    if projection != {
        "policy_orders_id": refs["policy_orders_ref"].get("policy_orders_id"),
        "schema_version": refs["policy_orders_ref"].get("schema_version"),
    }:
        raise SuiteFreezeError("policy orders reference differs from artifact")


def suite_id_for(value: dict[str, Any]) -> str:
    return _canonical_id("suite", value, "suite_id")


def validate_suite_manifest(
    manifest: dict[str, Any],
    *,
    root: Path,
    suite_path: Path,
    baseline_orchestrator: Path = DEFAULT_BASELINE_ORCHESTRATOR,
    enforce_pre_result_tree: bool = True,
) -> None:
    _strict_keys(manifest, SUITE_KEYS, "suite")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SuiteFreezeError("suite: unsupported schema version")
    if manifest.get("suite_id") != suite_id_for(manifest):
        raise SuiteFreezeError("suite: suite_id does not bind canonical manifest")
    if manifest.get("stage") != STAGE or manifest.get("phase") != "pre_verification_freeze":
        raise SuiteFreezeError("suite: invalid stage or phase")
    if manifest.get("target_count") != TARGET_COUNT:
        raise SuiteFreezeError("suite: target_count must be six")
    if manifest.get("proposal_count_per_target") != POOL_SIZE:
        raise SuiteFreezeError("suite: proposal_count_per_target must be 1024")
    sources = manifest.get("source_repositories")
    if not isinstance(sources, dict) or set(sources) != {
        "partizan",
        "astralbase",
        "bitmesh",
        "thermograph",
    }:
        raise SuiteFreezeError("suite: invalid source repository boundary")
    if any(HEX40.fullmatch(str(commit)) is None for commit in sources.values()):
        raise SuiteFreezeError("suite: source commits must be immutable")

    registry_ref = manifest.get("registry_ref")
    prereg_ref = manifest.get("preregistration_ref")
    implementation = manifest.get("implementation")
    if not isinstance(registry_ref, dict) or not isinstance(prereg_ref, dict):
        raise SuiteFreezeError("suite: registry and preregistration refs are required")
    _strict_keys(
        implementation,
        {"implementation_id", "partizan_commit", "components"},
        "suite.implementation",
    )
    registry_path = _resolve_bound_path(registry_ref.get("path"), root)
    registry, registry_raw, stage_targets = load_stage_a_targets(registry_path)
    if registry_ref != {
        "path": _repo_relative(registry_path, root),
        "registry_id": registry["registry_id"],
        "sha256": sha256_hex(registry_raw),
    }:
        raise SuiteFreezeError("suite: registry reference does not bind registry bytes")
    prereg_path = _resolve_bound_path(prereg_ref.get("path"), root)
    prereg_raw = prereg_path.read_bytes()
    if prereg_ref != {
        "path": _repo_relative(prereg_path, root),
        "preregistration_id": f"prereg-sha256:{sha256_hex(prereg_raw)}",
        "sha256": sha256_hex(prereg_raw),
    }:
        raise SuiteFreezeError("suite: preregistration reference mismatch")
    expected_implementation_id = _canonical_id(
        "implementation", implementation, "implementation_id"
    )
    if implementation.get("implementation_id") != expected_implementation_id:
        raise SuiteFreezeError("suite: implementation_id mismatch")
    if implementation.get("partizan_commit") != sources["partizan"]:
        raise SuiteFreezeError("suite: implementation commit differs from source boundary")
    components = implementation.get("components")
    if not isinstance(components, list) or len(components) != 3:
        raise SuiteFreezeError("suite: implementation must bind exactly three components")
    component_paths: set[str] = set()
    for index, component in enumerate(components):
        _strict_keys(component, {"path", "sha256"}, f"suite.implementation.components[{index}]")
        component_path = _resolve_bound_path(component["path"], root)
        if component["sha256"] != sha256_hex(component_path.read_bytes()):
            raise SuiteFreezeError(
                f"suite: implementation component hash mismatch: {component['path']}"
            )
        component_paths.add(component["path"])
    if len(component_paths) != 3:
        raise SuiteFreezeError("suite: implementation component paths must be unique")
    baseline_relative = _repo_relative(baseline_orchestrator, root)
    if baseline_relative not in component_paths:
        raise SuiteFreezeError("suite: baseline implementation is not bound")
    baseline_contract = _load_baseline_contract(baseline_orchestrator)

    seed_contract = manifest.get("seed_contract")
    if seed_contract != {
        "algorithm": "sha256_first_u64_big_endian_v1",
        "domain_hex": SEED_DOMAIN.hex(),
        "stage": STAGE,
        "target_id_encoding": "utf8",
    }:
        raise SuiteFreezeError("suite: seed contract differs from preregistration")
    boundary = manifest.get("freeze_boundary")
    if boundary != {
        "verifier_calls": 0,
        "results_artifacts_present": False,
        "policy_orders_frozen_before_verification": True,
        "wave70_material_present": False,
    }:
        raise SuiteFreezeError("suite: invalid pre-verification boundary")

    entries = manifest.get("targets")
    if not isinstance(entries, list) or len(entries) != TARGET_COUNT:
        raise SuiteFreezeError("suite: targets must contain exactly six entries")
    by_id = {item["target_spec"]["target_id"]: item for item in stage_targets}
    entry_ids = [entry.get("target_id") for entry in entries]
    expected_entry_ids = [item["target_spec"]["target_id"] for item in stage_targets]
    if entry_ids != expected_entry_ids or len(set(entry_ids)) != TARGET_COUNT:
        raise SuiteFreezeError("suite: target set differs from committed Stage A split")
    for entry in entries:
        _validate_target_artifacts(
            root=root,
            registry_item=by_id[entry["target_id"]],
            suite_entry=entry,
            source_repositories=sources,
            baseline_contract=baseline_contract,
        )
    if suite_path.read_bytes() != _canonical_bytes(manifest):
        raise SuiteFreezeError("suite manifest bytes are not canonical")

    if enforce_pre_result_tree:
        _validate_exact_pre_result_tree(
            manifest, root=root, suite_path=suite_path
        )


CommandRunner = Callable[[Sequence[str], Path], None]


def _run_command(command: Sequence[str], cwd: Path) -> None:
    result = subprocess.run(
        tuple(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SuiteFreezeError(
            f"command failed ({' '.join(command)}): {detail or 'no stderr'}"
        )


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _write_once_or_match(path: Path, value: bytes) -> None:
    """Write a derived artifact, refusing to replace different evidence."""

    if path.exists():
        if path.read_bytes() != value:
            raise SuiteFreezeError(f"existing derived artifact differs: {path}")
        return
    _write_bytes(path, value)


def _implementation_boundary(
    *, root: Path, partizan_commit: str, paths: Iterable[Path]
) -> dict[str, Any]:
    components = []
    for path in paths:
        components.append(
            {"path": _repo_relative(path, root), "sha256": sha256_hex(path.read_bytes())}
        )
    value: dict[str, Any] = {
        "implementation_id": "implementation-sha256:" + "0" * 64,
        "partizan_commit": partizan_commit,
        "components": components,
    }
    value["implementation_id"] = _canonical_id(
        "implementation", value, "implementation_id"
    )
    return value


def freeze_stage_a_suite(
    *,
    root: Path,
    registry_path: Path,
    preregistration_path: Path,
    output_root: Path,
    pool_orchestrator: Path,
    baseline_orchestrator: Path,
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    """Create one complete pre-verification Stage A suite."""

    root = root.resolve(strict=True)
    output_root = output_root.resolve()
    _repo_relative(output_root, root)
    expected_output_root = root / "data/discovery/wave_69/stage_a"
    if output_root != expected_output_root:
        raise SuiteFreezeError(
            "suite output must be data/discovery/wave_69/stage_a under the repository"
        )
    if output_root.exists() and any(output_root.iterdir()):
        raise SuiteFreezeError("suite output root must be absent or empty")

    source_repositories = {
        "astralbase": _clean_commit(astralbase_dir, "astralbase"),
        "bitmesh": _clean_commit(bitmesh_dir, "bitmesh"),
        "thermograph": _clean_commit(thermograph_dir, "thermograph"),
        "partizan": _clean_commit(root, "partizan"),
    }
    partizan_commit = source_repositories["partizan"]
    committed_inputs = (
        registry_path,
        preregistration_path,
        Path(__file__),
        pool_orchestrator,
        baseline_orchestrator,
    )
    for path in committed_inputs:
        _require_committed_bytes(root, path, partizan_commit)

    registry, registry_raw, stage_targets = load_stage_a_targets(registry_path)
    registry_sources = registry.get("source_boundary", {}).get(
        "clean_source_commits", {}
    )
    for name in ("astralbase", "bitmesh", "thermograph"):
        if source_repositories[name] != registry_sources.get(name):
            raise SuiteFreezeError(
                f"{name}: current clean commit differs from target-registry boundary"
            )

    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for registry_item in stage_targets:
        target = registry_item["target_spec"]
        target_id = target["target_id"]
        target_digest = target_id.split(":", 1)[1]
        target_dir = output_root / target_digest
        target_dir.mkdir(parents=True, exist_ok=False)
        target_path = target_dir / "target.json"
        proposals_path = target_dir / "proposals.jsonl"
        receipt_path = target_dir / "generation-receipt.json"
        pool_path = target_dir / "pool-manifest.json"
        policy_orders_path = target_dir / "policy-orders.json"
        _write_bytes(target_path, _canonical_bytes(target))
        seed = stage_seed(target_id)

        command_runner(
            (
                sys.executable,
                str(pool_orchestrator),
                "discovery-generate-pool-v1",
                "--target",
                str(target_path),
                "--output",
                str(proposals_path),
                "--receipt",
                str(receipt_path),
                "--pool-size",
                str(POOL_SIZE),
                "--random-seed",
                str(seed),
            ),
            root,
        )
        proposals, _ = _load_canonical_jsonl(proposals_path)
        if len(proposals) != POOL_SIZE:
            raise SuiteFreezeError("generator did not emit exactly 1024 proposals")

        command_runner(
            (
                sys.executable,
                str(pool_orchestrator),
                "discovery-freeze-pool",
                "--target",
                str(target_path),
                "--proposals",
                str(proposals_path),
                "--output",
                str(proposals_path),
                "--manifest",
                str(pool_path),
                "--candidate-artifact-path",
                _repo_relative(proposals_path, root),
                "--generation-receipt",
                str(receipt_path),
                "--astralbase-dir",
                str(astralbase_dir.resolve()),
                "--bitmesh-dir",
                str(bitmesh_dir.resolve()),
                "--thermograph-dir",
                str(thermograph_dir.resolve()),
            ),
            root,
        )
        pool, _ = _load_canonical_json(pool_path)
        receipt, _ = _load_canonical_json(receipt_path)

        command_runner(
            (
                sys.executable,
                str(baseline_orchestrator),
                "freeze",
                "--target",
                str(target_path),
                "--pool",
                str(pool_path),
                "--proposals",
                str(proposals_path),
                "--repository-root",
                str(root),
                "--output",
                str(policy_orders_path),
            ),
            root,
        )
        policy_orders, _ = _load_canonical_json(policy_orders_path)
        baseline_contract = _load_baseline_contract(baseline_orchestrator)
        policy_projection = _policy_orders_projection(
            policy_orders,
            target=target,
            pool=pool,
            proposals=proposals,
            proposals_path=proposals_path,
            root=root,
            baseline_contract=baseline_contract,
        )

        entry = {
            "target_id": target_id,
            "family": registry_item["family"],
            "bin_index": registry_item["bin"]["index"],
            "seed": seed,
            "target_ref": _artifact_ref(
                target_path,
                root,
                schema_version=discovery.TARGET_SCHEMA_VERSION,
                identifier_key="target_id",
                identifier=target_id,
            ),
            "proposals_ref": _artifact_ref(
                proposals_path,
                root,
                schema_version=discovery.PROPOSAL_SCHEMA_VERSION,
                row_count=POOL_SIZE,
            ),
            "generation_receipt_ref": _artifact_ref(
                receipt_path,
                root,
                schema_version=discovery.GENERATION_RECEIPT_SCHEMA_VERSION,
                identifier_key="receipt_id",
                identifier=receipt["receipt_id"],
            ),
            "pool_manifest_ref": _artifact_ref(
                pool_path,
                root,
                schema_version=discovery.POOL_SCHEMA_VERSION_V2,
                identifier_key="pool_id",
                identifier=pool["pool_id"],
            ),
            "policy_orders_ref": _artifact_ref(
                policy_orders_path,
                root,
                schema_version=policy_projection["schema_version"],
                identifier_key="policy_orders_id",
                identifier=policy_projection["policy_orders_id"],
            ),
        }
        entries.append(entry)
        _validate_target_artifacts(
            root=root,
            registry_item=registry_item,
            suite_entry=entry,
            source_repositories=source_repositories,
            baseline_contract=baseline_contract,
        )
        if _run_git(root, "status", "--porcelain", "--untracked-files=all"):
            raise SuiteFreezeError(
                "ignored suite generation unexpectedly dirtied the implementation tree"
            )

    prereg_raw = preregistration_path.read_bytes()
    implementation = _implementation_boundary(
        root=root,
        partizan_commit=partizan_commit,
        paths=(Path(__file__), pool_orchestrator, baseline_orchestrator),
    )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": "suite-sha256:" + "0" * 64,
        "stage": STAGE,
        "phase": "pre_verification_freeze",
        "registry_ref": {
            "path": _repo_relative(registry_path, root),
            "registry_id": registry["registry_id"],
            "sha256": sha256_hex(registry_raw),
        },
        "preregistration_ref": {
            "path": _repo_relative(preregistration_path, root),
            "preregistration_id": f"prereg-sha256:{sha256_hex(prereg_raw)}",
            "sha256": sha256_hex(prereg_raw),
        },
        "implementation": implementation,
        "source_repositories": source_repositories,
        "seed_contract": {
            "algorithm": "sha256_first_u64_big_endian_v1",
            "domain_hex": SEED_DOMAIN.hex(),
            "stage": STAGE,
            "target_id_encoding": "utf8",
        },
        "target_count": TARGET_COUNT,
        "proposal_count_per_target": POOL_SIZE,
        "targets": entries,
        "freeze_boundary": {
            "verifier_calls": 0,
            "results_artifacts_present": False,
            "policy_orders_frozen_before_verification": True,
            "wave70_material_present": False,
        },
    }
    manifest["suite_id"] = suite_id_for(manifest)
    suite_path = output_root / "suite-manifest.json"
    _write_bytes(suite_path, _canonical_bytes(manifest))
    validate_suite_manifest(
        manifest,
        root=root,
        suite_path=suite_path,
        baseline_orchestrator=baseline_orchestrator,
    )
    return manifest


def check_only(
    *, root: Path, suite_path: Path, baseline_orchestrator: Path
) -> dict[str, Any]:
    """Read and validate a suite without spawning any subprocess."""

    manifest, _ = _load_canonical_json(suite_path)
    validate_suite_manifest(
        manifest,
        root=root.resolve(strict=True),
        suite_path=suite_path,
        baseline_orchestrator=baseline_orchestrator,
    )
    return manifest


def finalize_baseline_input(
    *, root: Path, suite_path: Path, baseline_orchestrator: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Analyze existing ledgers and freeze the bound six-target suite inputs.

    This post-result step never invokes Astralbase. It deterministically reads
    ``verifier-results.jsonl`` beside each target bundle, recomputes the six
    baseline reports, builds ``baseline_suite_input.v0.1``, and validates the
    macro aggregate against the immutable pre-verification suite.
    """

    root = root.resolve(strict=True)
    suite_path = suite_path.absolute()
    expected_suite_path = root / "data/discovery/wave_69/stage_a/suite-manifest.json"
    if suite_path != expected_suite_path:
        raise SuiteFreezeError("baseline finalization requires the deterministic suite path")
    manifest, suite_raw = _load_canonical_json(suite_path)
    validate_suite_manifest(
        manifest,
        root=root,
        suite_path=suite_path,
        baseline_orchestrator=baseline_orchestrator,
        enforce_pre_result_tree=False,
    )
    baseline_contract = _load_baseline_contract(baseline_orchestrator)
    bundles: list[dict[str, Any]] = []
    for entry in manifest["targets"]:
        target_path = _resolve_bound_path(entry["target_ref"]["path"], root)
        proposals_path = _resolve_bound_path(entry["proposals_ref"]["path"], root)
        pool_path = _resolve_bound_path(entry["pool_manifest_ref"]["path"], root)
        orders_path = _resolve_bound_path(entry["policy_orders_ref"]["path"], root)
        target, _ = _load_canonical_json(target_path)
        proposals, _ = _load_canonical_jsonl(proposals_path)
        pool, _ = _load_canonical_json(pool_path)
        orders, _ = _load_canonical_json(orders_path)
        results_path = target_path.parent / RESULTS_FILENAME
        results, results_raw = _load_canonical_jsonl(results_path)
        if len(results) != POOL_SIZE:
            raise SuiteFreezeError(
                f"{results_path}: expected exactly {POOL_SIZE} verifier rows"
            )
        report = baseline_contract.analyze_baselines(
            target,
            pool,
            proposals,
            results,
            orders,
            proposals_path=proposals_path,
            repository_root=root,
        )
        report_path = target_path.parent / BASELINE_REPORT_FILENAME
        report_raw = _canonical_bytes(report)
        _write_once_or_match(report_path, report_raw)
        bundles.append(
            {
                "target_id": entry["target_id"],
                "pool_id": entry["pool_manifest_ref"]["pool_id"],
                "target_ref": entry["target_ref"],
                "pool_manifest_ref": entry["pool_manifest_ref"],
                "proposals_ref": entry["proposals_ref"],
                "policy_orders_ref": entry["policy_orders_ref"],
                "verifier_results_ref": {
                    "path": _repo_relative(results_path, root),
                    "schema_version": discovery.RESULT_SCHEMA_VERSION,
                    "sha256": sha256_hex(results_raw),
                    "row_count": len(results),
                },
                "baseline_report_ref": {
                    "path": _repo_relative(report_path, root),
                    "schema_version": baseline_contract.BASELINE_REPORT_SCHEMA_VERSION,
                    "report_id": report["report_id"],
                    "sha256": sha256_hex(report_raw),
                },
            }
        )

    pre_suite_ref = {
        "path": _repo_relative(suite_path, root),
        "schema_version": SCHEMA_VERSION,
        "suite_id": manifest["suite_id"],
        "sha256": sha256_hex(suite_raw),
    }
    suite_input = baseline_contract.build_baseline_suite_input(
        stage=STAGE,
        pre_verification_suite_ref=pre_suite_ref,
        bundles=bundles,
        repository_root=root,
    )
    input_errors = baseline_contract.validate_baseline_suite_input(
        suite_input, repository_root=root
    )
    if input_errors:
        raise SuiteFreezeError(
            "baseline suite input invalid: " + "; ".join(input_errors)
        )
    suite_report = baseline_contract.aggregate_baseline_suite(
        suite_input, repository_root=root
    )
    report_errors = baseline_contract.validate_baseline_suite_report(
        suite_report, suite_input, repository_root=root
    )
    if report_errors:
        raise SuiteFreezeError(
            "baseline suite report invalid: " + "; ".join(report_errors)
        )
    output_root = suite_path.parent
    _write_once_or_match(
        output_root / BASELINE_SUITE_INPUT_FILENAME,
        _canonical_bytes(suite_input),
    )
    _write_once_or_match(
        output_root / BASELINE_SUITE_REPORT_FILENAME,
        _canonical_bytes(suite_report),
    )
    return suite_input, suite_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--preregistration", type=Path, default=DEFAULT_PREREGISTRATION
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pool-orchestrator", type=Path, default=DEFAULT_POOL_ORCHESTRATOR)
    parser.add_argument(
        "--baseline-orchestrator", type=Path, default=DEFAULT_BASELINE_ORCHESTRATOR
    )
    parser.add_argument("--astralbase-dir", type=Path, default=DEFAULT_ASTRALBASE)
    parser.add_argument("--bitmesh-dir", type=Path, default=DEFAULT_BITMESH)
    parser.add_argument("--thermograph-dir", type=Path, default=DEFAULT_THERMOGRAPH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="Validate the existing suite manifest without commands or writes.",
    )
    mode.add_argument(
        "--finalize-baseline-input",
        action="store_true",
        help=(
            "Analyze deterministic verifier ledgers, build the bound baseline "
            "suite input, aggregate it, and validate both without verification."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repository_root.resolve(strict=True)
    try:
        if args.check_only:
            manifest = check_only(
                root=root,
                suite_path=args.output_root / "suite-manifest.json",
                baseline_orchestrator=args.baseline_orchestrator.resolve(strict=True),
            )
            print(f"wave69 Stage A suite check: ok ({manifest['suite_id']})")
            return 0
        if args.finalize_baseline_input:
            suite_input, suite_report = finalize_baseline_input(
                root=root,
                suite_path=args.output_root / "suite-manifest.json",
                baseline_orchestrator=args.baseline_orchestrator.resolve(strict=True),
            )
            print(
                "wave69 Stage A baseline finalization: ok "
                f"({suite_input['suite_input_id']}, {suite_report['suite_report_id']})"
            )
            return 0
        manifest = freeze_stage_a_suite(
            root=root,
            registry_path=args.registry.resolve(strict=True),
            preregistration_path=args.preregistration.resolve(strict=True),
            output_root=args.output_root,
            pool_orchestrator=args.pool_orchestrator.resolve(strict=True),
            baseline_orchestrator=args.baseline_orchestrator.resolve(strict=True),
            astralbase_dir=args.astralbase_dir.resolve(strict=True),
            bitmesh_dir=args.bitmesh_dir.resolve(strict=True),
            thermograph_dir=args.thermograph_dir.resolve(strict=True),
        )
    except (OSError, SuiteFreezeError, json.JSONDecodeError) as error:
        print(f"wave69 Stage A suite freeze failed: {error}", file=sys.stderr)
        return 1
    print(f"wave69 Stage A suite freeze: ok ({manifest['suite_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
