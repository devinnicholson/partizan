"""Narrow Python interface to the Partizan constrained-research engine."""

from ._native import analyze_subsystems, evaluate_position, find_locked_pawns
from .events import (
    EVENT_SCHEMA_VERSION,
    build_event_stream,
    canonical_event_bytes,
    validate_event_stream,
)
from .discovery import (
    POOL_SCHEMA_VERSION,
    PROPOSAL_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    RUN_SCHEMA_VERSION,
    TARGET_SCHEMA_VERSION,
    VALUE_RULE,
    build_ranker_input,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    validate_candidate_pool_manifest,
    validate_candidate_proposal,
    validate_discovery_bundle,
    validate_discovery_run,
    validate_target_spec,
    validate_verifier_result,
)

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "POOL_SCHEMA_VERSION",
    "PROPOSAL_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "RUN_SCHEMA_VERSION",
    "TARGET_SCHEMA_VERSION",
    "VALUE_RULE",
    "analyze_subsystems",
    "build_event_stream",
    "build_ranker_input",
    "canonical_json_bytes",
    "canonical_jsonl_bytes",
    "canonical_event_bytes",
    "evaluate_position",
    "find_locked_pawns",
    "validate_event_stream",
    "validate_candidate_pool_manifest",
    "validate_candidate_proposal",
    "validate_discovery_bundle",
    "validate_discovery_run",
    "validate_target_spec",
    "validate_verifier_result",
]
__version__ = "0.1.0"
