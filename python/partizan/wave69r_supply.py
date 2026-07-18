"""Pre-result freezer for the target-free Wave 69-R Gate S input suite.

This module generates only frozen inputs.  It never invokes Bitmesh,
Astralbase, Thermograph, or the Gate S checker binary.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_ROOT = (
    ROOT / "data/discovery/wave_69r/structural_supply/inputs"
)
DEFAULT_ASTRALBASE_DIR = ROOT.parent / "astralbase"
DEFAULT_BITMESH_DIR = ROOT.parent / "bitmesh"
DEFAULT_THERMOGRAPH_DIR = ROOT.parent / "thermograph"

BOARD_STREAM_SCHEMA = "partizan.candidate_board_stream.v0.1"
CERTIFICATE_SCHEMA = "partizan.structural_construction_certificate.v0.1"
RECEIPT_SCHEMA = "partizan.wave69r_supply_determinism_receipt.v0.1"
SHARD_MANIFEST_SCHEMA = "partizan.wave69r_supply_shard_manifest.v0.1"
SUITE_MANIFEST_SCHEMA = "partizan.wave69r_structural_supply_suite.v0.1"
CHECKER_REQUEST_SCHEMA = "partizan.wave69r_structural_supply_request.v0.1"
CATALOG_SCHEMA = "partizan.dfile_two_component_constructive_catalog.v0.2"
CATALOG_PATH = "docs/discovery_wave_69r_construction_catalog.v0.2.json"
GENERATOR_VERSION = "0.2.0"
GENERATOR_FAMILY = "dfile_two_component_constructive_grammar_v2"
GENERATOR_OPERATOR = "seeded_constructive_component_composition_v2"
CONSTRUCTION_CONTRACT = "partizan.dfile_two_component_constructive_grammar.v0.2"
PRODUCTION_SEED_DOMAIN = "partizan/w69r/supply/v1"
PRODUCTION_SHARD_COUNT = 4
PRODUCTION_ROWS_PER_SHARD = 1024
SERIALIZATION = "utf8-json-sort-keys-compact-newline-v1"
SOURCE_REPOSITORIES = ("partizan", "astralbase", "bitmesh", "thermograph")
IMPLEMENTATION_PARENT_COMMIT = "6ddd22af4adb7ff8f6f4c361a9132720a47e87b7"
PINNED_EXTERNAL_COMMITS = {
    "astralbase": "1434fca1fc04d97798ec1b820c56f52f8014ccc7",
    "bitmesh": "ade3417a007b9c8392d8a153abc4b3ed23edf0aa",
    "thermograph": "1d9b6b01c3921aca8c2a8fb13972fee8a4de5041",
}
STRATA = ("outer_leaper", "pawn_phalanx", "ray_cage", "mixed_color_hook")

_LOWER_HEX = set("0123456789abcdef")
_FORBIDDEN_KEYS = {
    "target",
    "target_id",
    "target_spec",
    "target_identity",
    "rank",
    "ranker_view",
    "label",
    "outcome",
    "result",
    "evaluator",
    "value_class",
}


class SupplyFreezeError(RuntimeError):
    """Raised before a partial or invalid supply suite can become authoritative."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SupplyFreezeError(f"cannot load implementation module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _orchestrator():
    return _load_module("partizan_wave69r_supply_orchestrator", ROOT / "engine/orchestrator.py")


def _gate_s():
    return _load_module("partizan_wave69r_supply_gate_s", ROOT / "python/partizan/gate_s.py")


def _discovery():
    return _load_module(
        "partizan_wave69r_supply_discovery", ROOT / "python/partizan/discovery.py"
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_bytes(values: Sequence[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(value) for value in values)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def derive_supply_seed(shard_index: int, *, domain: str = PRODUCTION_SEED_DOMAIN) -> int:
    if not isinstance(shard_index, int) or isinstance(shard_index, bool) or shard_index < 0:
        raise SupplyFreezeError("shard_index must be a non-negative integer")
    if not isinstance(domain, str) or not domain or "\0" in domain:
        raise SupplyFreezeError("seed domain must be a non-empty NUL-free string")
    try:
        domain_bytes = domain.encode("ascii")
    except UnicodeEncodeError as error:
        raise SupplyFreezeError("seed domain must contain only ASCII characters") from error
    digest = hashlib.sha256(
        domain_bytes + b"\0" + str(shard_index).encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def shard_id(shard_index: int) -> str:
    return f"wave69r-supply-shard-{shard_index}"


def _require_hex(value: Any, length: int, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in _LOWER_HEX for character in value)
    ):
        raise SupplyFreezeError(f"{path}: must be {length} lowercase hexadecimal characters")
    return value


def _exact_mapping(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SupplyFreezeError(f"{path}: must be an object")
    observed = set(value)
    if observed != keys:
        missing = sorted(keys - observed)
        extra = sorted(observed - keys)
        raise SupplyFreezeError(f"{path}: exact keys required; missing={missing}, extra={extra}")
    return value


def _relative_path(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SupplyFreezeError(f"{path}: must be a non-empty repository-relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or parsed.as_posix() != value:
        raise SupplyFreezeError(f"{path}: must be a normalized repository-relative path")
    return value


def _typed_id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-sha256:{sha256_hex(canonical_json_bytes(payload))}"


def _identity_without_id(prefix: str, value: dict[str, Any], id_key: str) -> str:
    payload = dict(value)
    payload[id_key] = f"{prefix}-sha256:" + "0" * 64
    return _typed_id(prefix, payload)


def _git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SupplyFreezeError(
            f"git inspection failed for {repository}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def clean_repository_commit(repository: Path, name: str) -> str:
    repository = repository.resolve(strict=True)
    commit = _require_hex(_git_output(repository, "rev-parse", "HEAD"), 40, f"{name}.commit")
    if _git_output(repository, "status", "--porcelain", "--untracked-files=all"):
        raise SupplyFreezeError(f"{name}: repository must be clean before suite generation")
    return commit


def collect_clean_repository_commits(
    *,
    partizan_dir: Path,
    astralbase_dir: Path,
    bitmesh_dir: Path,
    thermograph_dir: Path,
) -> dict[str, str]:
    directories = {
        "partizan": partizan_dir,
        "astralbase": astralbase_dir,
        "bitmesh": bitmesh_dir,
        "thermograph": thermograph_dir,
    }
    return {
        name: clean_repository_commit(directory, name)
        for name, directory in directories.items()
    }


def _validate_source_commit_map(commits: Any) -> dict[str, str]:
    checked = _exact_mapping(commits, set(SOURCE_REPOSITORIES), "source_repositories")
    for name, commit in checked.items():
        _require_hex(commit, 40, f"source_repositories.{name}")
    return checked


def _verify_production_source_boundary(
    commits: dict[str, str],
    *,
    partizan_dir: Path,
    expected_implementation_commit: str | None = None,
) -> None:
    checked = _validate_source_commit_map(commits)
    observed_external = {
        name: checked[name] for name in sorted(PINNED_EXTERNAL_COMMITS)
    }
    if observed_external != PINNED_EXTERNAL_COMMITS:
        raise SupplyFreezeError(
            "production external commits do not match the locked Wave 69-R pins"
        )
    implementation_commit = checked["partizan"]
    if expected_implementation_commit is not None:
        _require_hex(
            expected_implementation_commit, 40, "expected_implementation_commit"
        )
        if implementation_commit != expected_implementation_commit:
            raise SupplyFreezeError(
                "suite implementation commit does not match the explicit expected I"
            )
    parent_line = _git_output(
        partizan_dir.resolve(),
        "rev-list",
        "--parents",
        "-n",
        "1",
        implementation_commit,
    ).split()
    if parent_line != [implementation_commit, IMPLEMENTATION_PARENT_COMMIT]:
        raise SupplyFreezeError(
            "production implementation commit must be a direct child of Wave 69 E"
        )


def _require_commit_ancestor(
    *, repository: Path, ancestor: str, descendant: str
) -> None:
    result = subprocess.run(
        (
            "git",
            "-C",
            str(repository.resolve()),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode == 1:
        raise SupplyFreezeError(
            "suite implementation commit is not an ancestor of the clean current checkout"
        )
    if result.returncode:
        raise SupplyFreezeError(
            "git ancestry inspection failed: " + result.stderr.strip()
        )


def _scan_forbidden_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        forbidden = sorted(set(value) & _FORBIDDEN_KEYS)
        if forbidden:
            raise SupplyFreezeError(f"{path}: forbidden pre-result keys: {forbidden}")
        for key, item in value.items():
            _scan_forbidden_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_forbidden_keys(item, f"{path}[{index}]")


def _catalog_bundle(
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = repository_root / CATALOG_PATH
    try:
        raw = path.read_bytes()
        catalog = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupplyFreezeError(f"cannot read construction catalog: {error}") from error
    if not isinstance(catalog, dict):
        raise SupplyFreezeError("construction catalog must be a JSON object")
    catalog_errors = _discovery().validate_construction_catalog(catalog)
    if catalog_errors:
        raise SupplyFreezeError(
            "construction catalog contract failed: " + "; ".join(catalog_errors)
        )
    catalog_id = catalog.get("catalog_id")
    if not isinstance(catalog_id, str) or not catalog_id.startswith("catalog-sha256:"):
        raise SupplyFreezeError("construction catalog id is invalid")
    identity_input = dict(catalog)
    identity_input["catalog_id"] = "catalog-sha256:" + "0" * 64
    if catalog_id != _typed_id("catalog", identity_input):
        raise SupplyFreezeError("construction catalog id does not match canonical content")
    reference = {
        "path": CATALOG_PATH,
        "schema_version": CATALOG_SCHEMA,
        "catalog_id": catalog_id,
        "sha256": sha256_hex(raw),
    }
    return catalog, reference


def _run_generator_process(
    *, output_path: Path, row_count: int, seed: int, partizan_commit: str
) -> None:
    result = subprocess.run(
        (
            sys.executable,
            str(ROOT / "engine/orchestrator.py"),
            "discovery-generate-board-stream-v2-internal",
            "--output",
            str(output_path),
            "--pool-size",
            str(row_count),
            "--random-seed",
            str(seed),
            "--generator-code-commit",
            partizan_commit,
        ),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        if result.stderr:
            sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        raise SupplyFreezeError(
            f"separate-process generator failed with exit code {result.returncode}"
        )


def _load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupplyFreezeError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SupplyFreezeError(f"{path}: JSON bytes must be canonical")
    return value


def _load_canonical_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n") or b"\n\n" in raw:
        raise SupplyFreezeError(f"{path}: JSONL must be non-empty canonical rows")
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupplyFreezeError(f"{path}: invalid JSONL: {error}") from error
    if not all(isinstance(row, dict) for row in rows) or raw != canonical_jsonl_bytes(rows):
        raise SupplyFreezeError(f"{path}: JSONL bytes must be canonical")
    return rows


def _artifact_ref(
    *, path: str, schema_version: str, payload: bytes, row_count: int | None = None
) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "path": path,
        "schema_version": schema_version,
        "sha256": sha256_hex(payload),
    }
    if row_count is not None:
        reference["row_count"] = row_count
    return reference


def _certificate_rows(
    rows: list[dict[str, Any]], *, catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    discovery = _discovery()
    certificates: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        try:
            certificate = discovery.construction_certificate_for_board_row(row, catalog)
        except (KeyError, TypeError, ValueError) as error:
            raise SupplyFreezeError(
                f"construction certificate[{ordinal}] cannot be reconstructed: {error}"
            ) from error
        errors = discovery.validate_structural_construction_certificate(
            certificate, board_row=row, catalog=catalog
        )
        if errors:
            raise SupplyFreezeError(
                f"construction certificate[{ordinal}] invalid: {'; '.join(errors)}"
            )
        certificates.append(certificate)
    return certificates


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _freeze_shard(
    *,
    staging_root: Path,
    shard_index: int,
    row_count: int,
    seed_domain: str,
    commits: dict[str, str],
    catalog: dict[str, Any],
    catalog_ref: dict[str, Any],
) -> dict[str, Any]:
    frozen_id = shard_id(shard_index)
    seed = derive_supply_seed(shard_index, domain=seed_domain)
    shard_directory = staging_root / f"shard-{shard_index}"
    shard_directory.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix=f"{frozen_id}-") as temporary:
        run_paths = [Path(temporary) / "run-0.jsonl", Path(temporary) / "run-1.jsonl"]
        for run_path in run_paths:
            _run_generator_process(
                output_path=run_path,
                row_count=row_count,
                seed=seed,
                partizan_commit=commits["partizan"],
            )
        run_payloads = [path.read_bytes() for path in run_paths]
    if run_payloads[0] != run_payloads[1]:
        raise SupplyFreezeError(f"{frozen_id}: generator processes were not byte-identical")
    board_rows = [
        json.loads(line) for line in run_payloads[0].decode("utf-8").splitlines()
    ]
    if len(board_rows) != row_count:
        raise SupplyFreezeError(f"{frozen_id}: wrong generated row count")
    orchestrator = _orchestrator()
    for ordinal, row in enumerate(board_rows):
        errors = orchestrator.discovery_contract.validate_candidate_board_stream_row(row)
        if errors:
            raise SupplyFreezeError(f"{frozen_id}[{ordinal}]: {'; '.join(errors)}")
        if row["ordinal"] != ordinal:
            raise SupplyFreezeError(f"{frozen_id}: ordinals are not contiguous")
        if row["generator"]["code_commit"] != commits["partizan"]:
            raise SupplyFreezeError(f"{frozen_id}: row code commit drift")
        if row["generator"]["random_seed"] != seed:
            raise SupplyFreezeError(f"{frozen_id}: row seed drift")
        _scan_forbidden_keys(row)

    board_path = shard_directory / "board-stream.jsonl"
    _write_bytes(board_path, run_payloads[0])
    certificates = _certificate_rows(board_rows, catalog=catalog)
    certificate_payload = canonical_jsonl_bytes(certificates)
    certificate_path = shard_directory / "construction-certificates.jsonl"
    _write_bytes(certificate_path, certificate_payload)
    config = orchestrator._discovery_generator_config_v2(
        pool_size=row_count, random_seed=seed
    )
    config_sha = sha256_hex(canonical_json_bytes(config))
    if any(row["generator"]["config_sha256"] != config_sha for row in board_rows):
        raise SupplyFreezeError(f"{frozen_id}: generator config digest drift")

    relative_root = "data/discovery/wave_69r/structural_supply/inputs"
    relative_shard = f"{relative_root}/shard-{shard_index}"
    board_ref = _artifact_ref(
        path=f"{relative_shard}/board-stream.jsonl",
        schema_version=BOARD_STREAM_SCHEMA,
        payload=run_payloads[0],
        row_count=row_count,
    )
    certificate_ref = _artifact_ref(
        path=f"{relative_shard}/construction-certificates.jsonl",
        schema_version=CERTIFICATE_SCHEMA,
        payload=certificate_payload,
        row_count=row_count,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": "receipt-sha256:" + "0" * 64,
        "shard_id": frozen_id,
        "shard_index": shard_index,
        "seed_contract": {
            "algorithm": "sha256_first_u64_big_endian_v1",
            "domain": seed_domain,
            "index_encoding": "unpadded_ascii_decimal",
            "random_seed": seed,
        },
        "generator": {
            "name": "partizan_candidate_pool_generator",
            "version": GENERATOR_VERSION,
            "family": GENERATOR_FAMILY,
            "operator": GENERATOR_OPERATOR,
            "code_commit": commits["partizan"],
            "config": config,
            "config_sha256": config_sha,
        },
        "construction": {
            "contract": CONSTRUCTION_CONTRACT,
            "catalog_ref": catalog_ref,
            "certificate_artifact": certificate_ref,
        },
        "board_stream_artifact": board_ref,
        "executions": {
            "mode": "separate_python_processes_v1",
            "run_count": 2,
            "raw_artifact_sha256": [board_ref["sha256"], board_ref["sha256"]],
            "byte_identical": True,
        },
        "source_repositories": commits,
        "forbidden_calls": ["bitmesh", "astralbase", "thermograph", "gate_s_checker"],
    }
    receipt["receipt_id"] = _identity_without_id("receipt", receipt, "receipt_id")
    receipt_payload = canonical_json_bytes(receipt)
    receipt_path = shard_directory / "generation-report.json"
    _write_bytes(receipt_path, receipt_payload)
    receipt_ref = _artifact_ref(
        path=f"{relative_shard}/generation-report.json",
        schema_version=RECEIPT_SCHEMA,
        payload=receipt_payload,
    )

    manifest: dict[str, Any] = {
        "schema_version": SHARD_MANIFEST_SCHEMA,
        "manifest_id": "manifest-sha256:" + "0" * 64,
        "shard_id": frozen_id,
        "shard_index": shard_index,
        "row_count": row_count,
        "board_stream_ref": board_ref,
        "construction_certificate_ref": certificate_ref,
        "generation_report_ref": receipt_ref,
    }
    manifest["manifest_id"] = _identity_without_id("manifest", manifest, "manifest_id")
    manifest_payload = canonical_json_bytes(manifest)
    _write_bytes(shard_directory / "shard-manifest.json", manifest_payload)
    return {
        "manifest": manifest,
        "manifest_ref": _artifact_ref(
            path=f"{relative_shard}/shard-manifest.json",
            schema_version=SHARD_MANIFEST_SCHEMA,
            payload=manifest_payload,
        ),
        "board_rows": board_rows,
    }


def freeze_supply_suite(
    *,
    output_root: Path = DEFAULT_INPUT_ROOT,
    partizan_dir: Path = ROOT,
    astralbase_dir: Path = DEFAULT_ASTRALBASE_DIR,
    bitmesh_dir: Path = DEFAULT_BITMESH_DIR,
    thermograph_dir: Path = DEFAULT_THERMOGRAPH_DIR,
    shard_count: int = PRODUCTION_SHARD_COUNT,
    rows_per_shard: int = PRODUCTION_ROWS_PER_SHARD,
    seed_domain: str = PRODUCTION_SEED_DOMAIN,
) -> dict[str, Any]:
    """Generate, validate, and atomically freeze a complete pre-result suite."""

    if shard_count <= 0 or rows_per_shard <= 0:
        raise SupplyFreezeError("shard_count and rows_per_shard must be positive")
    if seed_domain == PRODUCTION_SEED_DOMAIN and (
        shard_count != PRODUCTION_SHARD_COUNT
        or rows_per_shard != PRODUCTION_ROWS_PER_SHARD
    ):
        raise SupplyFreezeError("production supply size is locked to four 1024-row shards")
    if partizan_dir.resolve() != ROOT.resolve():
        raise SupplyFreezeError(
            "partizan_dir must be the repository containing the loaded freezer"
        )
    output_root = output_root.resolve()
    expected_root = (partizan_dir.resolve() / "data/discovery/wave_69r/structural_supply/inputs")
    if output_root != expected_root and seed_domain == PRODUCTION_SEED_DOMAIN:
        raise SupplyFreezeError("production supply inputs must use the preregistered path")
    if output_root.exists():
        raise SupplyFreezeError("supply input root already exists; replacement is forbidden")
    commits = collect_clean_repository_commits(
        partizan_dir=partizan_dir,
        astralbase_dir=astralbase_dir,
        bitmesh_dir=bitmesh_dir,
        thermograph_dir=thermograph_dir,
    )
    if seed_domain == PRODUCTION_SEED_DOMAIN:
        _verify_production_source_boundary(commits, partizan_dir=partizan_dir)
    else:
        _validate_source_commit_map(commits)
    catalog, catalog_ref = _catalog_bundle(partizan_dir.resolve())
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="wave69r-supply-freeze-", dir=output_root.parent))
    try:
        shard_outputs = [
            _freeze_shard(
                staging_root=staging,
                shard_index=index,
                row_count=rows_per_shard,
                seed_domain=seed_domain,
                commits=commits,
                catalog=catalog,
                catalog_ref=catalog_ref,
            )
            for index in range(shard_count)
        ]
        all_rows = [row for output in shard_outputs for row in output["board_rows"]]
        expected_total = shard_count * rows_per_shard
        board_ids = [row["board_id"] for row in all_rows]
        reflections = [row["position"]["symmetry_sha256"] for row in all_rows]
        board_fields = [row["position"]["text"].split()[0] for row in all_rows]
        if len(all_rows) != expected_total:
            raise SupplyFreezeError("suite total row count drift")
        if len(set(board_ids)) != expected_total:
            raise SupplyFreezeError("suite board identities are not globally unique")
        if len(set(reflections)) != expected_total:
            raise SupplyFreezeError("suite reflection orbits are not globally unique")
        if len(set(board_fields)) != expected_total:
            raise SupplyFreezeError("suite board fields are not globally unique")

        board_paths = [staging / f"shard-{index}/board-stream.jsonl" for index in range(shard_count)]
        request_path = staging / "checker-requests.jsonl"
        gate_s = _gate_s()
        requests = gate_s.freeze_request_stream(
            board_paths, request_path, expected_row_count=expected_total
        )
        if any(request.get("schema_version") != CHECKER_REQUEST_SCHEMA for request in requests):
            raise SupplyFreezeError("checker request projection schema drift")
        request_payload = request_path.read_bytes()
        relative_root = "data/discovery/wave_69r/structural_supply/inputs"
        request_ref = _artifact_ref(
            path=f"{relative_root}/checker-requests.jsonl",
            schema_version=CHECKER_REQUEST_SCHEMA,
            payload=request_payload,
            row_count=expected_total,
        )
        stratum_counts = Counter(row["construction"]["stratum"] for row in all_rows)
        suite: dict[str, Any] = {
            "schema_version": SUITE_MANIFEST_SCHEMA,
            "suite_id": "suite-sha256:" + "0" * 64,
            "suite_name": "wave69r-target-free-structural-supply-inputs",
            "implementation_commit": commits["partizan"],
            "source_repositories": commits,
            "seed_contract": {
                "algorithm": "sha256_first_u64_big_endian_v1",
                "domain": seed_domain,
                "index_encoding": "unpadded_ascii_decimal",
                "shard_indices": list(range(shard_count)),
            },
            "catalog_ref": catalog_ref,
            "shards": [
                {
                    "shard_id": output["manifest"]["shard_id"],
                    "shard_index": output["manifest"]["shard_index"],
                    "manifest_ref": output["manifest_ref"],
                }
                for output in shard_outputs
            ],
            "checker_request_ref": request_ref,
            "totals": {
                "shard_count": shard_count,
                "rows_per_shard": rows_per_shard,
                "row_count": expected_total,
                "unique_board_id_count": len(set(board_ids)),
                "unique_reflection_orbit_count": len(set(reflections)),
                "unique_board_field_count": len(set(board_fields)),
                "stratum_counts": dict(sorted(stratum_counts.items())),
            },
            "pre_result_boundary": {
                "checker_invoked": False,
                "bitmesh_invoked": False,
                "astralbase_invoked": False,
                "thermograph_invoked": False,
                "target_fields_consumed": [],
                "stage_b_or_wave70_materialized": False,
            },
        }
        _scan_forbidden_keys(suite)
        suite["suite_id"] = _identity_without_id("suite", suite, "suite_id")
        _write_bytes(staging / "suite-manifest.json", canonical_json_bytes(suite))
        validate_supply_suite(
            input_root=staging,
            expected_shard_count=shard_count,
            expected_rows_per_shard=rows_per_shard,
            expected_seed_domain=seed_domain,
            expected_commits=commits,
            repository_root=partizan_dir.resolve(),
        )
        os.replace(staging, output_root)
        return suite
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _validate_ref(
    reference: Any,
    *,
    input_root: Path,
    repository_root: Path,
    expected_schema: str,
    row_count: int | None,
) -> Path:
    keys = {"path", "schema_version", "sha256"}
    if row_count is not None:
        keys.add("row_count")
    ref = _exact_mapping(reference, keys, "artifact_ref")
    if ref["schema_version"] != expected_schema:
        raise SupplyFreezeError("artifact_ref.schema_version drift")
    relative = _relative_path(ref["path"], "artifact_ref.path")
    if row_count is not None and ref["row_count"] != row_count:
        raise SupplyFreezeError("artifact_ref.row_count drift")
    # During atomic staging, refs retain their final repository paths.
    final_prefix = "data/discovery/wave_69r/structural_supply/inputs/"
    if not relative.startswith(final_prefix):
        raise SupplyFreezeError("artifact_ref.path is outside the frozen input root")
    local_relative = relative[len(final_prefix) :]
    path = input_root / local_relative
    if not path.is_file() or sha256_hex(path.read_bytes()) != ref["sha256"]:
        raise SupplyFreezeError(f"artifact_ref does not bind bytes: {relative}")
    return path


def validate_supply_suite(
    *,
    input_root: Path,
    expected_shard_count: int = PRODUCTION_SHARD_COUNT,
    expected_rows_per_shard: int = PRODUCTION_ROWS_PER_SHARD,
    expected_seed_domain: str = PRODUCTION_SEED_DOMAIN,
    expected_commits: dict[str, str] | None = None,
    expected_implementation_commit: str | None = None,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    """Check a frozen suite without generation or checker execution."""

    input_root = input_root.resolve(strict=True)
    expected_directories = {f"shard-{index}" for index in range(expected_shard_count)}
    expected_files = {"suite-manifest.json", "checker-requests.jsonl"}
    for index in range(expected_shard_count):
        expected_files.update(
            {
                f"shard-{index}/board-stream.jsonl",
                f"shard-{index}/construction-certificates.jsonl",
                f"shard-{index}/generation-report.json",
                f"shard-{index}/shard-manifest.json",
            }
        )
    discovered_directories: set[str] = set()
    discovered_files: set[str] = set()
    for path in input_root.rglob("*"):
        relative = path.relative_to(input_root).as_posix()
        if path.is_symlink():
            raise SupplyFreezeError(f"suite inventory may not contain symlinks: {relative}")
        if path.is_dir():
            discovered_directories.add(relative)
        elif path.is_file():
            discovered_files.add(relative)
        else:
            raise SupplyFreezeError(f"suite inventory contains a special file: {relative}")
    if discovered_directories != expected_directories or discovered_files != expected_files:
        raise SupplyFreezeError(
            "suite filesystem inventory drift; "
            f"directories={sorted(discovered_directories)}, files={sorted(discovered_files)}"
        )
    suite = _load_canonical_json(input_root / "suite-manifest.json")
    _exact_mapping(
        suite,
        {
            "schema_version",
            "suite_id",
            "suite_name",
            "implementation_commit",
            "source_repositories",
            "seed_contract",
            "catalog_ref",
            "shards",
            "checker_request_ref",
            "totals",
            "pre_result_boundary",
        },
        "suite",
    )
    if suite["schema_version"] != SUITE_MANIFEST_SCHEMA:
        raise SupplyFreezeError("suite schema drift")
    if suite["suite_id"] != _identity_without_id("suite", suite, "suite_id"):
        raise SupplyFreezeError("suite id drift")
    if expected_commits is None and expected_implementation_commit is None:
        raise SupplyFreezeError(
            "check requires current clean commits or an explicit expected I"
        )
    commits = _validate_source_commit_map(suite["source_repositories"])
    if suite["implementation_commit"] != commits["partizan"]:
        raise SupplyFreezeError("implementation commit is not the Partizan source commit")
    checked_expected_commits = None
    if expected_commits is not None:
        checked_expected_commits = _validate_source_commit_map(expected_commits)
        if expected_seed_domain == PRODUCTION_SEED_DOMAIN:
            for name in PINNED_EXTERNAL_COMMITS:
                if commits[name] != checked_expected_commits[name]:
                    raise SupplyFreezeError(
                        "suite external repository commits do not match current clean heads"
                    )
            _require_commit_ancestor(
                repository=repository_root,
                ancestor=commits["partizan"],
                descendant=checked_expected_commits["partizan"],
            )
        elif commits != checked_expected_commits:
            raise SupplyFreezeError("suite repository commits do not match expected pins")
    if expected_implementation_commit is not None:
        _require_hex(
            expected_implementation_commit, 40, "expected_implementation_commit"
        )
        if commits["partizan"] != expected_implementation_commit:
            raise SupplyFreezeError(
                "suite implementation commit does not match the explicit expected I"
            )
    if expected_seed_domain == PRODUCTION_SEED_DOMAIN:
        _verify_production_source_boundary(
            commits,
            partizan_dir=repository_root,
            expected_implementation_commit=expected_implementation_commit,
        )
    seed_contract = _exact_mapping(
        suite["seed_contract"],
        {"algorithm", "domain", "index_encoding", "shard_indices"},
        "seed_contract",
    )
    if seed_contract != {
        "algorithm": "sha256_first_u64_big_endian_v1",
        "domain": expected_seed_domain,
        "index_encoding": "unpadded_ascii_decimal",
        "shard_indices": list(range(expected_shard_count)),
    }:
        raise SupplyFreezeError("suite seed contract drift")
    catalog, catalog_reference = _catalog_bundle(repository_root)
    if suite["catalog_ref"] != catalog_reference:
        raise SupplyFreezeError("suite catalog reference drift")
    shards = suite["shards"]
    if not isinstance(shards, list) or len(shards) != expected_shard_count:
        raise SupplyFreezeError("suite shard inventory is incomplete")

    all_rows: list[dict[str, Any]] = []
    for index, shard_entry in enumerate(shards):
        entry = _exact_mapping(
            shard_entry, {"shard_id", "shard_index", "manifest_ref"}, f"shards[{index}]"
        )
        if entry["shard_id"] != shard_id(index) or entry["shard_index"] != index:
            raise SupplyFreezeError("suite shard order or identity drift")
        manifest_path = _validate_ref(
            entry["manifest_ref"],
            input_root=input_root,
            repository_root=repository_root,
            expected_schema=SHARD_MANIFEST_SCHEMA,
            row_count=None,
        )
        manifest = _load_canonical_json(manifest_path)
        _exact_mapping(
            manifest,
            {
                "schema_version",
                "manifest_id",
                "shard_id",
                "shard_index",
                "row_count",
                "board_stream_ref",
                "construction_certificate_ref",
                "generation_report_ref",
            },
            f"shard_manifest[{index}]",
        )
        if manifest["schema_version"] != SHARD_MANIFEST_SCHEMA:
            raise SupplyFreezeError("shard manifest schema drift")
        if manifest["manifest_id"] != _identity_without_id("manifest", manifest, "manifest_id"):
            raise SupplyFreezeError("shard manifest id drift")
        if (
            manifest["shard_id"] != shard_id(index)
            or manifest["shard_index"] != index
            or manifest["row_count"] != expected_rows_per_shard
        ):
            raise SupplyFreezeError("shard manifest identity/count drift")
        board_path = _validate_ref(
            manifest["board_stream_ref"],
            input_root=input_root,
            repository_root=repository_root,
            expected_schema=BOARD_STREAM_SCHEMA,
            row_count=expected_rows_per_shard,
        )
        certificate_path = _validate_ref(
            manifest["construction_certificate_ref"],
            input_root=input_root,
            repository_root=repository_root,
            expected_schema=CERTIFICATE_SCHEMA,
            row_count=expected_rows_per_shard,
        )
        receipt_path = _validate_ref(
            manifest["generation_report_ref"],
            input_root=input_root,
            repository_root=repository_root,
            expected_schema=RECEIPT_SCHEMA,
            row_count=None,
        )
        rows = _load_canonical_jsonl(board_path)
        certificates = _load_canonical_jsonl(certificate_path)
        receipt = _load_canonical_json(receipt_path)
        if len(rows) != expected_rows_per_shard or len(certificates) != len(rows):
            raise SupplyFreezeError("shard row/certificate count drift")
        gate_s = _gate_s()
        discovery = _discovery()
        for ordinal, (row, certificate) in enumerate(zip(rows, certificates)):
            gate_s.validate_board_stream_row(row)
            if row["ordinal"] != ordinal:
                raise SupplyFreezeError("shard ordinals are not contiguous")
            certificate_errors = discovery.validate_structural_construction_certificate(
                certificate, board_row=row, catalog=catalog
            )
            if certificate_errors:
                raise SupplyFreezeError(
                    "construction certificate sidecar drift: "
                    + "; ".join(certificate_errors)
                )
            _scan_forbidden_keys(row)
        _validate_receipt(
            receipt,
            shard_index=index,
            row_count=expected_rows_per_shard,
            seed_domain=expected_seed_domain,
            commits=commits,
            catalog_ref=suite["catalog_ref"],
            manifest=manifest,
        )
        all_rows.extend(rows)

    expected_total = expected_shard_count * expected_rows_per_shard
    board_ids = [row["board_id"] for row in all_rows]
    reflections = [row["position"]["symmetry_sha256"] for row in all_rows]
    board_fields = [row["position"]["text"].split()[0] for row in all_rows]
    if not (
        len(all_rows)
        == len(set(board_ids))
        == len(set(reflections))
        == len(set(board_fields))
        == expected_total
    ):
        raise SupplyFreezeError("suite global uniqueness/count contract failed")
    request_path = _validate_ref(
        suite["checker_request_ref"],
        input_root=input_root,
        repository_root=repository_root,
        expected_schema=CHECKER_REQUEST_SCHEMA,
        row_count=expected_total,
    )
    requests = _load_canonical_jsonl(request_path)
    gate_s = _gate_s()
    expected_requests = [gate_s.project_request(row) for row in all_rows]
    if requests != expected_requests:
        raise SupplyFreezeError("checker request projection drift")
    totals = suite["totals"]
    expected_strata = dict(
        sorted(Counter(row["construction"]["stratum"] for row in all_rows).items())
    )
    if totals != {
        "shard_count": expected_shard_count,
        "rows_per_shard": expected_rows_per_shard,
        "row_count": expected_total,
        "unique_board_id_count": expected_total,
        "unique_reflection_orbit_count": expected_total,
        "unique_board_field_count": expected_total,
        "stratum_counts": expected_strata,
    }:
        raise SupplyFreezeError("suite totals drift")
    expected_boundary = {
        "checker_invoked": False,
        "bitmesh_invoked": False,
        "astralbase_invoked": False,
        "thermograph_invoked": False,
        "target_fields_consumed": [],
        "stage_b_or_wave70_materialized": False,
    }
    if suite["pre_result_boundary"] != expected_boundary:
        raise SupplyFreezeError("suite pre-result boundary drift")
    _scan_forbidden_keys(suite)
    return suite


def _validate_receipt(
    receipt: dict[str, Any],
    *,
    shard_index: int,
    row_count: int,
    seed_domain: str,
    commits: dict[str, str],
    catalog_ref: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    _exact_mapping(
        receipt,
        {
            "schema_version",
            "receipt_id",
            "shard_id",
            "shard_index",
            "seed_contract",
            "generator",
            "construction",
            "board_stream_artifact",
            "executions",
            "source_repositories",
            "forbidden_calls",
        },
        "receipt",
    )
    if receipt["schema_version"] != RECEIPT_SCHEMA:
        raise SupplyFreezeError("receipt schema drift")
    if receipt["receipt_id"] != _identity_without_id("receipt", receipt, "receipt_id"):
        raise SupplyFreezeError("receipt id drift")
    if receipt["shard_id"] != shard_id(shard_index) or receipt["shard_index"] != shard_index:
        raise SupplyFreezeError("receipt shard identity drift")
    seed = derive_supply_seed(shard_index, domain=seed_domain)
    if receipt["seed_contract"] != {
        "algorithm": "sha256_first_u64_big_endian_v1",
        "domain": seed_domain,
        "index_encoding": "unpadded_ascii_decimal",
        "random_seed": seed,
    }:
        raise SupplyFreezeError("receipt seed derivation drift")
    generator = receipt["generator"]
    if not isinstance(generator, dict):
        raise SupplyFreezeError("receipt generator must be an object")
    orchestrator = _orchestrator()
    expected_config = orchestrator._discovery_generator_config_v2(
        pool_size=row_count, random_seed=seed
    )
    expected_config_sha = sha256_hex(canonical_json_bytes(expected_config))
    if generator != {
        "name": "partizan_candidate_pool_generator",
        "version": GENERATOR_VERSION,
        "family": GENERATOR_FAMILY,
        "operator": GENERATOR_OPERATOR,
        "code_commit": commits["partizan"],
        "config": expected_config,
        "config_sha256": expected_config_sha,
    }:
        raise SupplyFreezeError("receipt generator/config drift")
    if receipt["construction"] != {
        "contract": CONSTRUCTION_CONTRACT,
        "catalog_ref": catalog_ref,
        "certificate_artifact": manifest["construction_certificate_ref"],
    }:
        raise SupplyFreezeError("receipt construction binding drift")
    if receipt["board_stream_artifact"] != manifest["board_stream_ref"]:
        raise SupplyFreezeError("receipt board-stream binding drift")
    artifact_sha = manifest["board_stream_ref"]["sha256"]
    if receipt["executions"] != {
        "mode": "separate_python_processes_v1",
        "run_count": 2,
        "raw_artifact_sha256": [artifact_sha, artifact_sha],
        "byte_identical": True,
    }:
        raise SupplyFreezeError("receipt determinism evidence drift")
    if receipt["source_repositories"] != commits:
        raise SupplyFreezeError("receipt repository commits drift")
    if receipt["forbidden_calls"] != [
        "bitmesh",
        "astralbase",
        "thermograph",
        "gate_s_checker",
    ]:
        raise SupplyFreezeError("receipt forbidden-call boundary drift")
