"""Execute and audit the Wave 69-R Gate C calibration ledger.

This module is deliberately a thin orchestration layer.  The generic
Astralbase verifier remains the implementation in ``engine/orchestrator.py``
at the frozen implementation commit I.  Gate C calls that implementation once
per frozen target, retains every result, and performs no join until all six
1,024-row ledgers have passed the existing discovery result contract.
"""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
SUITE_MODULE_PATH = ROOT / "python/partizan/wave69r_gate_c_suite.py"
BASELINES_PATH = ROOT / "python/partizan/discovery_baselines.py"
DISCOVERY_PATH = ROOT / "python/partizan/discovery.py"
DEFAULT_SUITE_PATH = (
    ROOT / "data/discovery/wave_69r/calibration/inputs/suite-manifest.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "data/discovery/wave_69r/calibration/evidence"

SCHEMA_VERSION = "partizan.wave69r_gate_c_evidence.v0.1"
ANALYSIS_CONTRACT = "partizan.wave69r_gate_c_calibration_analysis.v0.1"
RESULT_SCHEMA_VERSION = "partizan.verifier_result.v0.1"
REPORT_SCHEMA_VERSION = "partizan.baseline_report.v0.1"
SUITE_REPORT_SCHEMA_VERSION = "partizan.baseline_suite_report.v0.1"
TARGET_COUNT = 6
PROPOSALS_PER_TARGET = 1024
TOTAL_RESULTS = TARGET_COUNT * PROPOSALS_PER_TARGET
MIN_MATCHES = 8
MIN_SYMMETRY_UNIQUE_MATCHES = 4
ANALYSIS_COMPONENT_PATHS = (
    "python/partizan/wave69r_gate_c_evidence.py",
    "scripts/run_wave69r_gate_c_evidence.py",
    "docs/schemas/partizan-wave69r-gate-c-evidence-v0.1.schema.json",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

EVIDENCE_KEYS = {
    "schema_version",
    "evidence_id",
    "evidence_kind",
    "analysis_contract",
    "decision",
    "temporal_boundary",
    "source_repositories",
    "analysis_implementation",
    "pre_result_suite_ref",
    "execution",
    "targets",
    "baseline_suite_report_ref",
    "totals",
    "scope_boundary",
}
TARGET_EVIDENCE_KEYS = {
    "target_id",
    "family",
    "bin_index",
    "results_ref",
    "baseline_report_ref",
    "counts",
    "gates",
    "target_decision",
}


class GateCEvidenceError(ValueError):
    """Raised without retrying or adapting a frozen calibration run."""


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    suite_contract = _load_module(SUITE_MODULE_PATH, "partizan_wave69r_ec_suite")
    baselines = _load_module(BASELINES_PATH, "partizan_wave69r_ec_baselines")
    discovery = _load_module(DISCOVERY_PATH, "partizan_wave69r_ec_discovery")
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE


def canonical_bytes(value: Any) -> bytes:
    return discovery.canonical_json_bytes(value)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity(prefix: str, value: dict[str, Any], key: str) -> str:
    payload = {name: item for name, item in value.items() if name != key}
    return f"{prefix}-sha256:{sha256_hex(canonical_bytes(payload))}"


def evidence_id_for(value: dict[str, Any]) -> str:
    return _identity("evidence", value, "evidence_id")


def _strict(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateCEvidenceError(f"{path}: must be an object")
    if set(value) != keys:
        raise GateCEvidenceError(
            f"{path}: keys differ; missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )
    return value


def _git(repo: Path, *arguments: str, allow_failure: bool = False) -> bytes:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode and not allow_failure:
        raise GateCEvidenceError(
            f"git {' '.join(arguments)} failed in {repo}: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result.stdout


def _head(repo: Path, *, clean: bool, detached: bool = False) -> str:
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if HEX40.fullmatch(commit) is None:
        raise GateCEvidenceError(f"{repo}: HEAD is not a full commit")
    if clean and _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise GateCEvidenceError(f"{repo}: repository must be clean")
    if detached:
        result = subprocess.run(
            ("git", "symbolic-ref", "-q", "HEAD"),
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            raise GateCEvidenceError(f"{repo}: implementation checkout must be detached")
    return commit


def _require_direct_parent(
    repo: Path, parent: str, child: str, label: str
) -> None:
    parents = _git(repo, "show", "-s", "--format=%P", child).decode("ascii").split()
    if parents != [parent]:
        raise GateCEvidenceError(f"temporal boundary is not exact direct ancestry: {label}")


def _require_exact_commit_inventory(
    repo: Path, *, commit: str, expected_paths: Sequence[str], label: str
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
        raise GateCEvidenceError(f"{label} commit diff inventory mismatch")
    for relative in expected:
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            raise GateCEvidenceError(f"{label} artifact is not regular: {relative}")
        if _git(repo, "show", f"{commit}:{relative}") != path.read_bytes():
            raise GateCEvidenceError(f"{label} committed bytes mismatch: {relative}")


def _repo_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise GateCEvidenceError(f"artifact is outside repository root: {path}") from error
    return PurePosixPath(*relative.parts).as_posix()


def _resolve(path: Any, root: Path) -> Path:
    if not isinstance(path, str) or not path:
        raise GateCEvidenceError("artifact path must be non-empty")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
        raise GateCEvidenceError(f"invalid repository-relative path: {path}")
    resolved = (root.resolve(strict=True) / Path(*parsed.parts)).resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise GateCEvidenceError(f"artifact reference escapes repository: {path}") from error
    return resolved


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateCEvidenceError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict) or payload != canonical_bytes(value):
        raise GateCEvidenceError(f"{path}: must be a canonical JSON object")
    return value, payload


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
        lines = payload.decode("utf-8").splitlines()
        if not lines or any(not line for line in lines):
            raise ValueError("JSONL must be non-empty and contain no blank rows")
        values = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise GateCEvidenceError(f"cannot load JSONL {path}: {error}") from error
    if not all(isinstance(value, dict) for value in values):
        raise GateCEvidenceError(f"{path}: every JSONL row must be an object")
    if payload != discovery.canonical_jsonl_bytes(values):
        raise GateCEvidenceError(f"{path}: bytes are not canonical JSONL")
    return values, payload


def _load_ref(
    reference: dict[str, Any], root: Path, *, schema: str, jsonl: bool,
    rows: int | None = None,
) -> tuple[Any, bytes, Path]:
    path = _resolve(reference.get("path"), root)
    if reference.get("schema_version") != schema:
        raise GateCEvidenceError(f"artifact schema mismatch: {path}")
    value, payload = _load_jsonl(path) if jsonl else _load_json(path)
    if reference.get("sha256") != sha256_hex(payload):
        raise GateCEvidenceError(f"artifact hash mismatch: {path}")
    if rows is not None:
        if reference.get("row_count") != rows or len(value) != rows:
            raise GateCEvidenceError(f"artifact row count mismatch: {path}")
    return value, payload, path


def _artifact_ref(
    path: Path, root: Path, *, schema: str, rows: int | None = None,
    id_key: str | None = None, identifier: str | None = None,
) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "path": _repo_relative(path, root),
        "schema_version": schema,
        "sha256": sha256_hex(path.read_bytes()),
    }
    if rows is not None:
        reference["row_count"] = rows
    if id_key is not None:
        reference[id_key] = identifier
    return reference


def _committed_suite_boundary(
    *, root: Path, suite_path: Path, manifest: dict[str, Any],
    implementation_root: Path, astralbase_dir: Path, bitmesh_dir: Path,
    thermograph_dir: Path, require_artifact_clean: bool,
    expected_pre_result_commit: str | None = None,
) -> dict[str, str]:
    if expected_pre_result_commit is None:
        p_c = _head(root, clean=require_artifact_clean)
    else:
        p_c = expected_pre_result_commit
        if HEX40.fullmatch(p_c) is None:
            raise GateCEvidenceError("P_c is not a full commit")
    suite_relative = _repo_relative(suite_path, root)
    if _git(root, "show", f"{p_c}:{suite_relative}") != suite_path.read_bytes():
        raise GateCEvidenceError("P_c does not commit the exact pre-result suite bytes")

    sources = manifest["source_repositories"]
    i_commit = sources["partizan"]
    if _head(implementation_root, clean=True, detached=True) != i_commit:
        raise GateCEvidenceError("clean detached implementation checkout is not I")
    observed_external = {
        "astralbase": _head(astralbase_dir, clean=True),
        "bitmesh": _head(bitmesh_dir, clean=True),
        "thermograph": _head(thermograph_dir, clean=True),
    }
    if observed_external != {name: sources[name] for name in observed_external}:
        raise GateCEvidenceError("external repository pins differ from P_c")
    for relative in ANALYSIS_COMPONENT_PATHS:
        path = _resolve(relative, root)
        if _git(root, "show", f"{i_commit}:{relative}") != path.read_bytes():
            raise GateCEvidenceError(
                f"Gate C analysis component differs from frozen I: {relative}"
            )

    gate_ref = manifest["gate_s_go_ref"]
    gate_evidence, _, _ = _load_ref(
        gate_ref,
        root,
        schema=suite_contract.GATE_S_EVIDENCE_SCHEMA_VERSION,
        jsonl=False,
    )
    p_s = gate_evidence["supply_pre_result"]["commit"]
    e_s = manifest["temporal_boundary"]["gate_s_evidence_commit"]
    commits = [i_commit, p_s, e_s, p_c]
    if len(set(commits)) != 4 or any(HEX40.fullmatch(value) is None for value in commits):
        raise GateCEvidenceError("I, P_s, E_s, and P_c must be four distinct commits")
    _require_direct_parent(root, i_commit, p_s, "I -> P_s")
    _require_direct_parent(root, p_s, e_s, "P_s -> E_s")
    _require_direct_parent(root, e_s, p_c, "E_s -> P_c")
    return {
        "implementation_commit": i_commit,
        "supply_pre_result_commit": p_s,
        "supply_evidence_commit": e_s,
        "calibration_pre_result_commit": p_c,
    }


def validate_complete_ledger(
    *, target: dict[str, Any], pool: dict[str, Any],
    proposals: list[dict[str, Any]], results: list[dict[str, Any]],
    expected_rows: int = PROPOSALS_PER_TARGET,
) -> None:
    """Apply the existing result contract and exact generator-order join."""

    if len(proposals) != expected_rows or len(results) != expected_rows:
        raise GateCEvidenceError("ledger must retain exactly one row per proposal")
    proposal_ids = [row.get("proposal_id") for row in proposals]
    result_proposal_ids = [row.get("proposal_id") for row in results]
    if result_proposal_ids != proposal_ids or len(set(result_proposal_ids)) != expected_rows:
        raise GateCEvidenceError("ledger must preserve exact frozen generator order")
    result_ids: list[Any] = []
    for index, (proposal, result) in enumerate(zip(proposals, results)):
        errors = discovery.validate_verifier_result(result, target, proposal)
        if errors:
            raise GateCEvidenceError(f"result[{index}] invalid: {'; '.join(errors)}")
        if result.get("verifier", {}).get("code_commits") != pool.get("source_repositories"):
            raise GateCEvidenceError(f"result[{index}] does not preserve all four pins")
        result_ids.append(result.get("result_id"))
    if len(set(result_ids)) != expected_rows:
        raise GateCEvidenceError("ledger result ids must be unique")


def _analyze_target(
    *, target: dict[str, Any], pool: dict[str, Any],
    proposals: list[dict[str, Any]], results: list[dict[str, Any]],
    policy_orders: dict[str, Any], proposals_path: Path,
    production_policy: bool = True,
) -> dict[str, Any]:
    """Compatibility projection onto the already frozen Wave 69 metrics."""

    validate_complete_ledger(
        target=target, pool=pool, proposals=proposals, results=results
    )
    suite_contract.validate_policy_orders(
        policy_orders, target, pool, proposals, production=production_policy
    )
    proposal_ids = [row["proposal_id"] for row in proposals]
    proposals_by_id = {row["proposal_id"]: row for row in proposals}
    results_by_id = {row["proposal_id"]: row for row in results}
    heuristic_ids = baselines.heuristic_order(proposals)
    random_replicates = []
    for order in policy_orders["random_policy"]["orders"]:
        ordered_ids = baselines.stable_random_permutation(proposal_ids, order["seed"])
        random_replicates.append(
            {
                "order_id": order["order_id"],
                "replicate": order["replicate"],
                "metrics": baselines._metrics_for_order(
                    ordered_ids, proposals_by_id, results_by_id, target
                ),
            }
        )
    ordinal = baselines._order_commitment(
        target_id=target["target_id"],
        pool_id=pool["pool_id"],
        policy="generator_ordinal_audit",
        replicate=None,
        seed=None,
        ordered_ids=proposal_ids,
    )
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": "baseline-report-sha256:" + "0" * 64,
        "target_id": target["target_id"],
        "pool_id": pool["pool_id"],
        "input_bindings": {
            "target_sha256": sha256_hex(canonical_bytes(target)),
            "pool_sha256": sha256_hex(canonical_bytes(pool)),
            "proposals_sha256": sha256_hex(discovery.canonical_jsonl_bytes(proposals)),
            "results_sha256": sha256_hex(discovery.canonical_jsonl_bytes(results)),
            "result_row_count": len(results),
            "policy_orders_id": policy_orders["policy_orders_id"],
            "policy_orders_sha256": sha256_hex(canonical_bytes(policy_orders)),
        },
        "join_contract": {
            "mode": "one_complete_frozen_ledger_no_verifier_rerun",
            "every_proposal_consumes_one_call": True,
            "proposal_count": len(proposals),
            "result_count": len(results),
            "result_order_matches_proposal_order": True,
        },
        "metric_contract": {
            "budgets": list(baselines.METRIC_BUDGETS),
            "success": "verified_match_with_exact_target_value_class_and_structural_sha256",
            "distinctness": "proposal.position.symmetry_sha256",
            "outcome_rate_keys": list(baselines.RATE_KEYS),
            "naudc_method": baselines.NAUDC_METHOD,
            "percentile_method": baselines.PERCENTILE_METHOD,
        },
        "heuristic": {
            "order_id": policy_orders["heuristic_policy"]["order"]["order_id"],
            "metrics": baselines._metrics_for_order(
                heuristic_ids, proposals_by_id, results_by_id, target
            ),
        },
        "generator_ordinal_audit": {
            "competitive_baseline": False,
            "order_id": ordinal["order_id"],
            "metrics": baselines._metrics_for_order(
                proposal_ids, proposals_by_id, results_by_id, target
            ),
        },
        "random": {
            "replicates": random_replicates,
            "summary": baselines._random_summary(random_replicates, len(proposals)),
        },
    }
    report["report_id"] = baselines.baseline_report_id_for(report)
    return report


def target_counts(
    proposals: list[dict[str, Any]], results: list[dict[str, Any]]
) -> dict[str, int]:
    outcomes = Counter(row["outcome"] for row in results)
    symmetry = {
        proposal["position"]["symmetry_sha256"]
        for proposal, result in zip(proposals, results)
        if result["outcome"] == "certified_target"
    }
    return {
        "certified_matches": outcomes["certified_target"],
        "certified_nonmatches": outcomes["certified_other"],
        "rejections": outcomes["rejected"],
        "internal_errors": outcomes["error"],
        "certified_coverage_numerator": (
            outcomes["certified_target"] + outcomes["certified_other"]
        ),
        "certified_coverage_denominator": len(results),
        "symmetry_unique_matches": len(symmetry),
    }


def target_gates(counts: dict[str, int]) -> dict[str, bool]:
    denominator = counts["certified_coverage_denominator"]
    return {
        "coverage_at_least_95_percent": (
            counts["certified_coverage_numerator"] * 100 >= 95 * denominator
        ),
        "certified_matches_at_least_8": counts["certified_matches"] >= MIN_MATCHES,
        "symmetry_unique_matches_at_least_4": (
            counts["symmetry_unique_matches"] >= MIN_SYMMETRY_UNIQUE_MATCHES
        ),
        "internal_errors_zero": counts["internal_errors"] == 0,
    }


def categorized_decision(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the preregistered Construction > Semantic outcome precedence."""

    errors = [row["target_id"] for row in targets if not row["gates"]["internal_errors_zero"]]
    coverage = [
        row["target_id"]
        for row in targets
        if not row["gates"]["coverage_at_least_95_percent"]
    ]
    semantic = [
        row["target_id"]
        for row in targets
        if not row["gates"]["certified_matches_at_least_8"]
        or not row["gates"]["symmetry_unique_matches_at_least_4"]
    ]
    construction = [
        row["target_id"]
        for row in targets
        if row["target_id"] in set(errors) | set(coverage)
    ]
    if construction:
        category, status, failing = "Construction", "NO-GO", construction
    elif semantic:
        category, status, failing = "Semantic", "NO-GO", semantic
    else:
        category, status, failing = "Calibration", "GO", []
    return {
        "category": category,
        "status": status,
        "failing_target_ids": failing,
        "stage_b_automatically_opened": False,
    }


def _totals(targets: list[dict[str, Any]]) -> dict[str, int]:
    keys = tuple(targets[0]["counts"]) if targets else ()
    return {
        "target_count": len(targets),
        "result_count": sum(row["counts"]["certified_coverage_denominator"] for row in targets),
        **{key: sum(row["counts"][key] for row in targets) for key in keys if key != "certified_coverage_denominator"},
    }


def _suite_analysis_input_id(manifest: dict[str, Any], reports: list[dict[str, Any]]) -> str:
    payload = {
        "gate_c_suite_id": manifest["suite_id"],
        "target_report_ids": [row["report_id"] for row in reports],
    }
    return "baseline-suite-input-sha256:" + sha256_hex(canonical_bytes(payload))


def _analysis_implementation(root: Path, implementation_commit: str) -> dict[str, Any]:
    return {
        "partizan_commit": implementation_commit,
        "components": [
            {
                "path": relative,
                "sha256": sha256_hex(_resolve(relative, root).read_bytes()),
            }
            for relative in ANALYSIS_COMPONENT_PATHS
        ],
    }


def _expected_inventory(evidence: dict[str, Any], root: Path, evidence_path: Path) -> None:
    output_root = root / "data/discovery/wave_69r/calibration/evidence"
    if evidence_path.resolve() != (output_root / "gate-c-evidence.json").resolve():
        raise GateCEvidenceError("Gate C evidence path is not deterministic")
    expected = {"gate-c-evidence.json", "baseline-suite-report.json"}
    expected_target_files = {"verifier-results.jsonl", "baseline-report.json"}
    inodes: set[tuple[int, int]] = set()
    for row in evidence["targets"]:
        digest = row["target_id"].split(":", 1)[1]
        expected.add(digest)
        directory = output_root / digest
        if directory.is_symlink() or not directory.is_dir():
            raise GateCEvidenceError("evidence target directory must be real")
        if {path.name for path in directory.iterdir()} != expected_target_files:
            raise GateCEvidenceError("evidence target inventory differs")
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file():
                raise GateCEvidenceError("evidence artifacts must be regular files")
            inode = (path.stat().st_dev, path.stat().st_ino)
            if inode in inodes:
                raise GateCEvidenceError("evidence artifacts may not alias by hard link")
            inodes.add(inode)
    if {path.name for path in output_root.iterdir()} != expected:
        raise GateCEvidenceError("Gate C evidence tree contains an unexpected artifact")


def _target_inputs(
    entry: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], Path]:
    target, _, _ = _load_ref(
        entry["target_ref"], root, schema=discovery.TARGET_SCHEMA_VERSION, jsonl=False
    )
    proposals, _, proposals_path = _load_ref(
        entry["proposals_ref"], root, schema=discovery.PROPOSAL_SCHEMA_VERSION,
        jsonl=True, rows=PROPOSALS_PER_TARGET,
    )
    pool, _, _ = _load_ref(
        entry["pool_manifest_ref"], root,
        schema=discovery.POOL_SCHEMA_VERSION_V3, jsonl=False,
    )
    policy, _, _ = _load_ref(
        entry["policy_orders_ref"], root,
        schema=suite_contract.POLICY_SCHEMA_VERSION, jsonl=False,
    )
    return target, pool, proposals, policy, proposals_path


def _build_expected_evidence(
    *, root: Path, manifest: dict[str, Any], suite_path: Path,
    temporal: dict[str, str], evidence_path: Path,
) -> dict[str, Any]:
    target_evidence: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for entry in manifest["targets"]:
        target, pool, proposals, policy, proposals_path = _target_inputs(entry, root)
        digest = entry["target_id"].split(":", 1)[1]
        target_dir = evidence_path.parent / digest
        results_path = target_dir / "verifier-results.jsonl"
        report_path = target_dir / "baseline-report.json"
        results, _, _ = _load_ref(
            {
                "path": _repo_relative(results_path, root),
                "schema_version": RESULT_SCHEMA_VERSION,
                "sha256": sha256_hex(results_path.read_bytes()),
                "row_count": PROPOSALS_PER_TARGET,
            },
            root,
            schema=RESULT_SCHEMA_VERSION,
            jsonl=True,
            rows=PROPOSALS_PER_TARGET,
        )
        report, report_payload = _load_json(report_path)
        expected_report = _analyze_target(
            target=target,
            pool=pool,
            proposals=proposals,
            results=results,
            policy_orders=policy,
            proposals_path=proposals_path,
        )
        if report != expected_report:
            raise GateCEvidenceError("baseline report differs from ledger-only recomputation")
        reports.append(report)
        counts = target_counts(proposals, results)
        gates = target_gates(counts)
        target_evidence.append(
            {
                "target_id": entry["target_id"],
                "family": entry["family"],
                "bin_index": entry["bin_index"],
                "results_ref": _artifact_ref(
                    results_path, root, schema=RESULT_SCHEMA_VERSION,
                    rows=PROPOSALS_PER_TARGET,
                ),
                "baseline_report_ref": {
                    "path": _repo_relative(report_path, root),
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "report_id": report["report_id"],
                    "sha256": sha256_hex(report_payload),
                },
                "counts": counts,
                "gates": gates,
                "target_decision": "GO" if all(gates.values()) else "NO-GO",
            }
        )
    suite_report_path = evidence_path.parent / "baseline-suite-report.json"
    suite_report, suite_report_payload = _load_json(suite_report_path)
    expected_suite_report = baselines._aggregate_validated_reports(
        reports,
        stage="stage_a",
        suite_input_id=_suite_analysis_input_id(manifest, reports),
    )
    if suite_report != expected_suite_report:
        raise GateCEvidenceError("suite report differs from exact six-report recomputation")
    suite_payload = suite_path.read_bytes()
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": "evidence-sha256:" + "0" * 64,
        "evidence_kind": "calibration_only_not_paper_evidence",
        "analysis_contract": ANALYSIS_CONTRACT,
        "decision": categorized_decision(target_evidence),
        "temporal_boundary": temporal,
        "source_repositories": manifest["source_repositories"],
        "analysis_implementation": _analysis_implementation(
            root, temporal["implementation_commit"]
        ),
        "pre_result_suite_ref": {
            "path": _repo_relative(suite_path, root),
            "schema_version": suite_contract.SCHEMA_VERSION,
            "suite_id": manifest["suite_id"],
            "sha256": sha256_hex(suite_payload),
        },
        "execution": {
            "mode": "one_generic_astralbase_batch_per_target_v1",
            "generic_verifier_process_count": TARGET_COUNT,
            "proposal_count_per_target": PROPOSALS_PER_TARGET,
            "total_proposals": TOTAL_RESULTS,
            "proposal_verifier_call_count": TOTAL_RESULTS,
            "generator_order_preserved": True,
            "retries": 0,
            "adaptive_actions": 0,
            "join_after_all_ledgers_complete": True,
        },
        "targets": target_evidence,
        "baseline_suite_report_ref": {
            "path": _repo_relative(suite_report_path, root),
            "schema_version": SUITE_REPORT_SCHEMA_VERSION,
            "suite_report_id": suite_report["suite_report_id"],
            "sha256": sha256_hex(suite_report_payload),
        },
        "totals": _totals(target_evidence),
        "scope_boundary": {
            "stage_b_material_present": False,
            "wave70_material_present": False,
            "paper_evidence_claim": False,
            "automatic_follow_on_execution": False,
        },
    }
    evidence["evidence_id"] = evidence_id_for(evidence)
    return evidence


def validate_evidence_shape(evidence: dict[str, Any]) -> None:
    _strict(evidence, EVIDENCE_KEYS, "evidence")
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise GateCEvidenceError("evidence schema mismatch")
    if evidence.get("evidence_id") != evidence_id_for(evidence):
        raise GateCEvidenceError("evidence identity mismatch")
    if evidence.get("evidence_kind") != "calibration_only_not_paper_evidence":
        raise GateCEvidenceError("evidence kind exceeds calibration scope")
    if evidence.get("analysis_contract") != ANALYSIS_CONTRACT:
        raise GateCEvidenceError("analysis contract mismatch")
    decision = _strict(
        evidence.get("decision"),
        {"category", "status", "failing_target_ids", "stage_b_automatically_opened"},
        "evidence.decision",
    )
    if decision.get("category") not in {"Integrity", "Construction", "Semantic", "Calibration"}:
        raise GateCEvidenceError("decision category invalid")
    if decision.get("status") not in {"GO", "NO-GO"} or decision.get("stage_b_automatically_opened") is not False:
        raise GateCEvidenceError("decision status or automatic action invalid")
    temporal = _strict(
        evidence.get("temporal_boundary"),
        {"implementation_commit", "supply_pre_result_commit", "supply_evidence_commit", "calibration_pre_result_commit"},
        "evidence.temporal_boundary",
    )
    if any(HEX40.fullmatch(str(value)) is None for value in temporal.values()):
        raise GateCEvidenceError("temporal commits invalid")
    sources = _strict(
        evidence.get("source_repositories"),
        {"partizan", "astralbase", "bitmesh", "thermograph"},
        "evidence.source_repositories",
    )
    if any(HEX40.fullmatch(str(value)) is None for value in sources.values()):
        raise GateCEvidenceError("source pins invalid")
    analysis = _strict(
        evidence.get("analysis_implementation"),
        {"partizan_commit", "components"},
        "evidence.analysis_implementation",
    )
    if analysis.get("partizan_commit") != sources.get("partizan"):
        raise GateCEvidenceError("analysis implementation commit differs from I")
    components = analysis.get("components")
    if (
        not isinstance(components, list)
        or [row.get("path") for row in components]
        != list(ANALYSIS_COMPONENT_PATHS)
    ):
        raise GateCEvidenceError("analysis implementation inventory mismatch")
    for index, component in enumerate(components):
        _strict(component, {"path", "sha256"}, f"analysis.components[{index}]")
        if HEX64.fullmatch(str(component.get("sha256"))) is None:
            raise GateCEvidenceError("analysis component digest invalid")
    entries = evidence.get("targets")
    if not isinstance(entries, list) or len(entries) != TARGET_COUNT:
        raise GateCEvidenceError("evidence must contain exactly six targets")
    for index, row in enumerate(entries):
        _strict(row, TARGET_EVIDENCE_KEYS, f"evidence.targets[{index}]")
    if evidence.get("scope_boundary") != {
        "stage_b_material_present": False,
        "wave70_material_present": False,
        "paper_evidence_claim": False,
        "automatic_follow_on_execution": False,
    }:
        raise GateCEvidenceError("scope boundary invalid")


def check_only(
    *, root: Path, implementation_root: Path, suite_path: Path,
    evidence_path: Path, astralbase_dir: Path, bitmesh_dir: Path,
    thermograph_dir: Path, require_evidence_commit: bool = False,
) -> dict[str, Any]:
    """Recompute every E_c claim without importing or invoking a verifier."""

    root = root.resolve(strict=True)
    evidence, _ = _load_json(evidence_path)
    validate_evidence_shape(evidence)
    p_c = evidence["temporal_boundary"]["calibration_pre_result_commit"]
    manifest = suite_contract.validate_committed_pre_result(
        root=root,
        suite_path=suite_path,
        pre_result_commit=p_c,
        require_current_head=False,
    )
    temporal = _committed_suite_boundary(
        root=root,
        suite_path=suite_path,
        manifest=manifest,
        implementation_root=implementation_root.resolve(strict=True),
        astralbase_dir=astralbase_dir.resolve(strict=True),
        bitmesh_dir=bitmesh_dir.resolve(strict=True),
        thermograph_dir=thermograph_dir.resolve(strict=True),
        require_artifact_clean=False,
        expected_pre_result_commit=p_c,
    )
    expected = _build_expected_evidence(
        root=root,
        manifest=manifest,
        suite_path=suite_path,
        temporal=temporal,
        evidence_path=evidence_path,
    )
    if evidence != expected:
        raise GateCEvidenceError("evidence differs from check-only recomputation")
    _expected_inventory(evidence, root, evidence_path)
    if require_evidence_commit:
        evidence_commit = _head(root, clean=True)
        _require_direct_parent(root, p_c, evidence_commit, "P_c -> E_c")
        evidence_relative = _repo_relative(evidence_path, root)
        if _git(root, "show", f"{evidence_commit}:{evidence_relative}") != evidence_path.read_bytes():
            raise GateCEvidenceError("E_c does not commit the exact evidence bytes")
        evidence_root = evidence_path.parent
        evidence_paths = sorted(
            path.relative_to(root).as_posix()
            for path in evidence_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        _require_exact_commit_inventory(
            root,
            commit=evidence_commit,
            expected_paths=[
                *evidence_paths,
                "docs/discovery_wave_69r_calibration_report.json",
            ],
            label="Gate C evidence E_c",
        )
    return evidence


VerifierRunner = Callable[..., list[dict[str, Any]]]


def _generic_verifier_runner(
    *, implementation_root: Path, artifact_root: Path,
    target_path: Path, proposals_path: Path, manifest_path: Path,
    output_path: Path, astralbase_dir: Path, bitmesh_dir: Path,
    thermograph_dir: Path, source_repositories: dict[str, str],
) -> list[dict[str, Any]]:
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        orchestrator = _load_module(
            implementation_root / "engine/orchestrator.py",
            "partizan_wave69r_ec_frozen_orchestrator",
        )
    finally:
        sys.dont_write_bytecode = previous_bytecode
    return orchestrator.verify_discovery_pool(
        target_path=target_path,
        proposals_path=proposals_path,
        manifest_path=manifest_path,
        results_output_path=output_path,
        astralbase_dir=astralbase_dir,
        bitmesh_dir=bitmesh_dir,
        thermograph_dir=thermograph_dir,
        current_repositories=source_repositories,
        repository_root=artifact_root,
    )


def _finalize_evidence_output(
    *,
    artifact_root: Path,
    implementation_root: Path,
    suite_path: Path,
    output_root: Path,
    manifest: dict[str, Any],
    temporal: dict[str, str],
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
) -> dict[str, Any]:
    """Write and revalidate E_c, removing the entire tree on failure."""

    try:
        evidence_path = output_root / "gate-c-evidence.json"
        evidence = _build_expected_evidence(
            root=artifact_root,
            manifest=manifest,
            suite_path=suite_path,
            temporal=temporal,
            evidence_path=evidence_path,
        )
        evidence_path.write_bytes(canonical_bytes(evidence))
        validate_evidence_shape(evidence)
        return check_only(
            root=artifact_root,
            implementation_root=implementation_root,
            suite_path=suite_path,
            evidence_path=evidence_path,
            astralbase_dir=astralbase_dir,
            bitmesh_dir=bitmesh_dir,
            thermograph_dir=thermograph_dir,
        )
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def execute_gate_c(
    *, artifact_root: Path, implementation_root: Path, suite_path: Path,
    output_root: Path, astralbase_dir: Path, bitmesh_dir: Path,
    thermograph_dir: Path, verifier_runner: VerifierRunner = _generic_verifier_runner,
) -> dict[str, Any]:
    """Run exactly the committed P_c suite, once, without retry or adaptation."""

    artifact_root = artifact_root.resolve(strict=True)
    implementation_root = implementation_root.resolve(strict=True)
    suite_path = suite_path.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root != artifact_root / "data/discovery/wave_69r/calibration/evidence":
        raise GateCEvidenceError("Gate C output root is not deterministic")
    if output_root.exists():
        raise GateCEvidenceError("Gate C output root must be absent")
    manifest = suite_contract.check_only(root=artifact_root, suite_path=suite_path)
    temporal = _committed_suite_boundary(
        root=artifact_root,
        suite_path=suite_path,
        manifest=manifest,
        implementation_root=implementation_root,
        astralbase_dir=astralbase_dir.resolve(strict=True),
        bitmesh_dir=bitmesh_dir.resolve(strict=True),
        thermograph_dir=thermograph_dir.resolve(strict=True),
        require_artifact_clean=True,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="wave69r-gate-c-evidence-", dir=output_root.parent
    ) as temporary:
        temporary_root = Path(temporary)
        # Phase 1: verifier only.  There is intentionally no retry branch and no
        # policy join in this loop.
        for entry in manifest["targets"]:
            digest = entry["target_id"].split(":", 1)[1]
            results_path = temporary_root / digest / "verifier-results.jsonl"
            results_path.parent.mkdir(parents=True, exist_ok=True)
            verifier_runner(
                implementation_root=implementation_root,
                artifact_root=artifact_root,
                target_path=_resolve(entry["target_ref"]["path"], artifact_root),
                proposals_path=_resolve(entry["proposals_ref"]["path"], artifact_root),
                manifest_path=_resolve(entry["pool_manifest_ref"]["path"], artifact_root),
                output_path=results_path,
                astralbase_dir=astralbase_dir.resolve(strict=True),
                bitmesh_dir=bitmesh_dir.resolve(strict=True),
                thermograph_dir=thermograph_dir.resolve(strict=True),
                source_repositories=manifest["source_repositories"],
            )

        # Phase 2 starts only after all six raw ledgers exist and validate.
        contexts = []
        for entry in manifest["targets"]:
            target, pool, proposals, policy, proposals_path = _target_inputs(
                entry, artifact_root
            )
            digest = entry["target_id"].split(":", 1)[1]
            results_path = temporary_root / digest / "verifier-results.jsonl"
            results, _, = _load_jsonl(results_path)
            validate_complete_ledger(
                target=target, pool=pool, proposals=proposals, results=results
            )
            contexts.append((entry, target, pool, proposals, policy, proposals_path, results))

        reports = []
        for entry, target, pool, proposals, policy, proposals_path, results in contexts:
            report = _analyze_target(
                target=target,
                pool=pool,
                proposals=proposals,
                results=results,
                policy_orders=policy,
                proposals_path=proposals_path,
            )
            reports.append(report)
            digest = entry["target_id"].split(":", 1)[1]
            (temporary_root / digest / "baseline-report.json").write_bytes(
                canonical_bytes(report)
            )
        suite_report = baselines._aggregate_validated_reports(
            reports,
            stage="stage_a",
            suite_input_id=_suite_analysis_input_id(manifest, reports),
        )
        (temporary_root / "baseline-suite-report.json").write_bytes(
            canonical_bytes(suite_report)
        )
        temporary_root.rename(output_root)
    return _finalize_evidence_output(
        artifact_root=artifact_root,
        implementation_root=implementation_root,
        suite_path=suite_path,
        output_root=output_root,
        manifest=manifest,
        temporal=temporal,
        astralbase_dir=astralbase_dir,
        bitmesh_dir=bitmesh_dir,
        thermograph_dir=thermograph_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wave 69-R Gate C evidence lane")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--implementation-root", type=Path, required=True)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--astralbase-dir", type=Path, required=True)
    parser.add_argument("--bitmesh-dir", type=Path, required=True)
    parser.add_argument("--thermograph-dir", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact_root = args.root.resolve()
    suite_path = args.suite or artifact_root / DEFAULT_SUITE_PATH.relative_to(ROOT)
    output_root = args.output_root or artifact_root / DEFAULT_OUTPUT_ROOT.relative_to(ROOT)
    if args.check_only:
        evidence = check_only(
            root=artifact_root,
            implementation_root=args.implementation_root,
            suite_path=suite_path,
            evidence_path=output_root / "gate-c-evidence.json",
            astralbase_dir=args.astralbase_dir,
            bitmesh_dir=args.bitmesh_dir,
            thermograph_dir=args.thermograph_dir,
            require_evidence_commit=True,
        )
    else:
        evidence = execute_gate_c(
            artifact_root=artifact_root,
            implementation_root=args.implementation_root,
            suite_path=suite_path,
            output_root=output_root,
            astralbase_dir=args.astralbase_dir,
            bitmesh_dir=args.bitmesh_dir,
            thermograph_dir=args.thermograph_dir,
        )
    print(
        "wave69r-gate-c-evidence: ok "
        f"(category={evidence['decision']['category']}, "
        f"status={evidence['decision']['status']}, results={TOTAL_RESULTS})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
