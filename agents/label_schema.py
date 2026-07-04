#!/usr/bin/env python3
"""Validate Partizan dataset label JSONL rows."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re


ROOT = Path(__file__).resolve().parent
DEFAULT_VALID_FIXTURE = ROOT / "fixtures" / "label_rows.valid.jsonl"
DEFAULT_INVALID_FIXTURE = ROOT / "fixtures" / "label_rows.invalid.jsonl"

SCHEMA_VERSION = "partizan.dataset_label.v0"
LABEL_KINDS = {"exact", "rejected", "heuristic", "prediction"}
LABEL_PAYLOAD_KEYS = ("exact", "rejected", "heuristic", "prediction")

COMMON_REQUIRED_FIELDS = ("schema_version", "row_id", "domain", "position", "label_kind")
POSITION_REQUIRED_FIELDS = ("encoding", "text")
EXACT_REQUIRED_FIELDS = ("status", "value", "value_class")
EXACT_PROVENANCE_REQUIRED_FIELDS = (
    "code_commit",
    "generator",
    "generator_config_hash",
    "random_seed",
    "domain_definition",
    "verifier",
    "verifier_version",
    "certificate",
)
CERTIFICATE_REQUIRED_FIELDS = ("kind", "digest")
COMPOSITION_CERTIFICATE_FIELDS = (
    "decomposition_digest",
    "composition_digest",
    "component_values",
    "result_value_digest",
)
COMPOSITION_CERTIFICATE_KIND_PREFIX = "bitmesh-bmcompose-v1+thermograph-exact-value"
REJECTED_REQUIRED_FIELDS = ("status", "reasons")
REJECTED_STATUSES = {"unsupported", "error", "excluded"}
HEURISTIC_REQUIRED_FIELDS = ("method", "method_version", "outputs")
PREDICTION_REQUIRED_FIELDS = ("model_id", "model_version", "checkpoint", "outputs")
LEGACY_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{16}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
ROOT_RE = re.compile(r"^(?:[0-9]|[1-5][0-9]|6[0-3])$")

AMBIGUOUS_TOP_LEVEL_FIELDS = {
    "components",
    "error",
    "expanded_nodes",
    "label",
    "mean_value",
    "temperature",
}


@dataclass(frozen=True)
class ValidationIssue:
    """A single JSONL row validation problem."""

    path: Path
    line_number: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line_number}: {self.message}"


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _require_mapping(
    row: dict[str, Any], key: str, errors: list[str]
) -> dict[str, Any] | None:
    value = row.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return None
    return value


def _require_fields(
    mapping: dict[str, Any], fields: tuple[str, ...], context: str, errors: list[str]
) -> None:
    for field in fields:
        if field not in mapping:
            errors.append(f"{context} missing required field {field}")
        elif not _is_non_empty(mapping[field]):
            errors.append(f"{context}.{field} must be non-empty")


def validate_row(row: Any) -> list[str]:
    """Return validation errors for one parsed JSONL row."""

    errors: list[str] = []
    if not isinstance(row, dict):
        return ["row must be a JSON object"]

    _require_fields(row, COMMON_REQUIRED_FIELDS, "row", errors)

    for field in AMBIGUOUS_TOP_LEVEL_FIELDS:
        if field in row:
            errors.append(
                f"top-level {field} is ambiguous; use the label_kind payload object"
            )

    schema_version = row.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    label_kind = row.get("label_kind")
    if label_kind not in LABEL_KINDS:
        errors.append(
            f"label_kind must be one of {', '.join(sorted(LABEL_KINDS))}"
        )

    position = _require_mapping(row, "position", errors)
    if position is not None:
        _require_fields(position, POSITION_REQUIRED_FIELDS, "position", errors)

    payload_keys = [key for key in LABEL_PAYLOAD_KEYS if key in row]
    if len(payload_keys) != 1:
        errors.append(
            "row must contain exactly one label payload object: "
            + ", ".join(LABEL_PAYLOAD_KEYS)
        )
    elif label_kind in LABEL_KINDS and payload_keys[0] != label_kind:
        errors.append(
            f"label_kind {label_kind!r} does not match payload {payload_keys[0]!r}"
        )

    if label_kind == "exact":
        _validate_exact(row, errors)
    elif label_kind == "rejected":
        _validate_rejected(row, errors)
    elif label_kind == "heuristic":
        _validate_heuristic(row, errors)
    elif label_kind == "prediction":
        _validate_prediction(row, errors)

    return errors


def _validate_exact(row: dict[str, Any], errors: list[str]) -> None:
    exact = _require_mapping(row, "exact", errors)
    if exact is not None:
        _require_fields(exact, EXACT_REQUIRED_FIELDS, "exact", errors)
        if exact.get("status") != "verified":
            errors.append("exact.status must be 'verified'")
        value = exact.get("value")
        if isinstance(value, dict):
            digest = value.get("digest")
            if digest is not None and not _is_digest_like(digest):
                errors.append("exact.value.digest must be a digest-like string")

    provenance = _require_mapping(row, "provenance", errors)
    if provenance is not None:
        _require_fields(
            provenance,
            EXACT_PROVENANCE_REQUIRED_FIELDS,
            "provenance",
            errors,
        )
        _validate_certificate(provenance.get("certificate"), exact, errors)


def _validate_certificate(
    certificate: Any, exact: dict[str, Any] | None, errors: list[str]
) -> None:
    if not isinstance(certificate, dict):
        errors.append("provenance.certificate must be an object")
        return

    _require_fields(
        certificate,
        CERTIFICATE_REQUIRED_FIELDS,
        "provenance.certificate",
        errors,
    )
    if "digest" in certificate and not _is_digest_like(certificate.get("digest")):
        errors.append("provenance.certificate.digest must be a digest-like string")

    has_composition_fields = any(
        field in certificate for field in COMPOSITION_CERTIFICATE_FIELDS
    )
    if not has_composition_fields:
        return

    _require_fields(
        certificate,
        COMPOSITION_CERTIFICATE_FIELDS,
        "provenance.certificate",
        errors,
    )

    kind = certificate.get("kind")
    if not isinstance(kind, str) or not kind.startswith(COMPOSITION_CERTIFICATE_KIND_PREFIX):
        errors.append(
            "provenance.certificate.kind with composition fields must start with "
            f"{COMPOSITION_CERTIFICATE_KIND_PREFIX!r}"
        )

    for digest_field in (
        "decomposition_digest",
        "composition_digest",
        "result_value_digest",
    ):
        if digest_field in certificate and not _is_digest_like(certificate.get(digest_field)):
            errors.append(f"provenance.certificate.{digest_field} must be a digest-like string")

    exact_value = exact.get("value") if isinstance(exact, dict) else None
    if isinstance(exact_value, dict):
        exact_digest = exact_value.get("digest")
        result_digest = certificate.get("result_value_digest")
        if _is_non_empty(exact_digest) and _is_non_empty(result_digest):
            if str(exact_digest) != str(result_digest):
                errors.append(
                    "provenance.certificate.result_value_digest must match "
                    "exact.value.digest"
                )

    component_values = certificate.get("component_values")
    if not isinstance(component_values, dict) or not component_values:
        errors.append(
            "provenance.certificate.component_values must be a non-empty "
            "object mapping component roots to value digests"
        )
        return

    for component_root, value_digest in component_values.items():
        if not isinstance(component_root, str) or not component_root.strip():
            errors.append(
                "provenance.certificate.component_values keys must be non-empty strings"
            )
        elif not ROOT_RE.fullmatch(component_root.strip()):
            errors.append(
                "provenance.certificate.component_values keys must be square roots 0..63"
            )
        if not isinstance(value_digest, str) or not value_digest.strip():
            errors.append(
                "provenance.certificate.component_values values must be non-empty strings"
            )
        elif not _is_digest_like(value_digest):
            errors.append(
                "provenance.certificate.component_values values must be digest-like strings"
            )

    if isinstance(exact_value, dict) and _is_non_empty(exact_value.get("component_count")):
        try:
            declared_count = int(str(exact_value["component_count"]))
        except ValueError:
            errors.append("exact.value.component_count must be an integer when present")
        else:
            if declared_count != len(component_values):
                errors.append(
                    "exact.value.component_count must match "
                    "provenance.certificate.component_values"
                )


def _is_digest_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if LEGACY_HEX_DIGEST_RE.fullmatch(text) or SHA256_HEX_RE.fullmatch(text):
        return True
    if text.startswith("sha256:") and len(text) > len("sha256:"):
        return True
    if text.startswith("thermograph:") and len(text) > len("thermograph:"):
        return True
    if text.startswith("bitmesh:") and len(text) > len("bitmesh:"):
        return True
    return False


def _validate_rejected(row: dict[str, Any], errors: list[str]) -> None:
    rejected = _require_mapping(row, "rejected", errors)
    if rejected is None:
        return

    _require_fields(rejected, REJECTED_REQUIRED_FIELDS, "rejected", errors)
    if rejected.get("status") not in REJECTED_STATUSES:
        errors.append(
            "rejected.status must be one of "
            + ", ".join(sorted(REJECTED_STATUSES))
        )

    reasons = rejected.get("reasons")
    if not isinstance(reasons, list) or not all(
        isinstance(reason, str) and reason.strip() for reason in reasons
    ):
        errors.append("rejected.reasons must be a non-empty list of strings")


def _validate_heuristic(row: dict[str, Any], errors: list[str]) -> None:
    heuristic = _require_mapping(row, "heuristic", errors)
    if heuristic is not None:
        _require_fields(
            heuristic, HEURISTIC_REQUIRED_FIELDS, "heuristic", errors
        )


def _validate_prediction(row: dict[str, Any], errors: list[str]) -> None:
    prediction = _require_mapping(row, "prediction", errors)
    if prediction is not None:
        _require_fields(
            prediction, PREDICTION_REQUIRED_FIELDS, "prediction", errors
        )


def validate_jsonl(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                issues.append(
                    ValidationIssue(path, line_number, "blank JSONL row is ambiguous")
                )
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append(
                    ValidationIssue(path, line_number, f"invalid JSON: {error.msg}")
                )
                continue

            for message in validate_row(row):
                issues.append(ValidationIssue(path, line_number, message))

    return issues


def _print_issues(issues: list[ValidationIssue]) -> None:
    for issue in issues:
        print(issue.format(), file=sys.stderr)


def validate_command(paths: list[Path]) -> int:
    all_issues: list[ValidationIssue] = []
    row_count = 0

    for path in paths:
        if not path.exists():
            all_issues.append(ValidationIssue(path, 0, "file does not exist"))
            continue
        row_count += sum(1 for _ in path.open("r", encoding="utf-8"))
        all_issues.extend(validate_jsonl(path))

    if all_issues:
        _print_issues(all_issues)
        print(f"labels: invalid ({len(all_issues)} issue(s))", file=sys.stderr)
        return 1

    print(f"labels: ok ({row_count} row(s))")
    return 0


def self_test_command() -> int:
    valid_issues = validate_jsonl(DEFAULT_VALID_FIXTURE)
    invalid_issues = validate_jsonl(DEFAULT_INVALID_FIXTURE)

    if valid_issues:
        _print_issues(valid_issues)
        print("label schema self-test: valid fixture failed", file=sys.stderr)
        return 1

    if not invalid_issues:
        print(
            "label schema self-test: invalid fixture unexpectedly passed",
            file=sys.stderr,
        )
        return 1

    print(
        "label schema self-test: ok "
        f"({DEFAULT_VALID_FIXTURE.name} passed, "
        f"{DEFAULT_INVALID_FIXTURE.name} rejected with "
        f"{len(invalid_issues)} issue(s))"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate_parser = subcommands.add_parser("validate")
    validate_parser.add_argument(
        "jsonl_paths",
        type=Path,
        nargs="+",
        help="JSONL dataset row files to validate.",
    )

    subcommands.add_parser("self-test")

    args = parser.parse_args()

    if args.command == "validate":
        return validate_command(args.jsonl_paths)
    if args.command == "self-test":
        return self_test_command()

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
