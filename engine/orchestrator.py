#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


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

    return parser


def cli_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
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
