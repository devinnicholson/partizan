"""Narrow Python interface to the Partizan constrained-research engine."""

from importlib import import_module

from . import fixed_value as _fixed_value
from .discovery import (
    GENERATION_RECEIPT_SCHEMA_VERSION,
    POOL_SCHEMA_VERSION,
    POOL_SCHEMA_VERSION_V2,
    PROPOSAL_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    RUN_SCHEMA_VERSION,
    TARGET_SCHEMA_VERSION,
    VALUE_RULE,
    build_ranker_input,
    candidate_state_key_for,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    fen_file_reflection_orbit_sha256,
    generation_receipt_id_for,
    partizan_pool_features_for_fen,
    validate_candidate_pool_manifest,
    validate_candidate_proposal,
    validate_discovery_bundle,
    validate_discovery_run,
    validate_generation_receipt,
    validate_target_spec,
    validate_verifier_result,
)
from .fixed_value import (
    LiteralGameStats,
    ShortGameComparison,
    build_repertoire,
    canonicalize_literal_game,
    compare_repertoire_entries,
    compare_short_games,
    inspect_repertoire,
    literal_game_sha256,
    representation_sha256,
    validate_repertoire,
)

FIXED_VALUE_CANDIDATE_SCHEMA_VERSION = _fixed_value.CANDIDATE_SCHEMA_VERSION
FIXED_VALUE_CERTIFICATE_SCHEMA_VERSION = _fixed_value.CERTIFICATE_SCHEMA_VERSION
FIXED_VALUE_REPERTOIRE_SCHEMA_VERSION = _fixed_value.REPERTOIRE_SCHEMA_VERSION
FIXED_VALUE_TARGET_SCHEMA_VERSION = _fixed_value.TARGET_SCHEMA_VERSION
fixed_value_candidate_id_for = _fixed_value.candidate_id_for
fixed_value_target_id_for = _fixed_value.target_id_for
generate_fixed_value_candidates = _fixed_value.generate_candidates
make_fixed_value_candidate = _fixed_value.make_candidate
make_fixed_value_target = _fixed_value.make_target
validate_fixed_value_candidate = _fixed_value.validate_candidate
validate_fixed_value_target = _fixed_value.validate_target

_LAZY_NATIVE_EXPORTS = {
    "analyze_subsystems": "analyze_subsystems",
    "evaluate_position": "evaluate_position",
    "find_locked_pawns": "find_locked_pawns",
    "replay_chess_witness": "replay_chess_witness",
}
_LAZY_CHESS_EXPORTS = {
    "CHESS_ADAPTER_DOMAIN_ID": "DOMAIN_ID",
    "CHESS_ADAPTER_PROJECTION_DOMAIN_ID": "PROJECTION_DOMAIN_ID",
    "CHESS_ADAPTER_PROJECTION_RULE": "PROJECTION_RULE",
    "CHESS_ADAPTER_SCHEMA_VERSION": "ADAPTER_SCHEMA_VERSION",
    "adapt_chess_position": "adapt_chess_position",
    "chess_adapter_id_for": "adapter_id_for",
    "fixed_value_candidate_from_chess_adapter": "candidate_from_adapter",
    "fixed_value_target_from_chess_adapter": "target_from_adapter",
    "validate_chess_adapter_record": "validate_chess_adapter_record",
}
_LAZY_EVENT_EXPORTS = {
    "EVENT_SCHEMA_VERSION": "EVENT_SCHEMA_VERSION",
    "build_event_stream": "build_event_stream",
    "canonical_event_bytes": "canonical_event_bytes",
    "validate_event_stream": "validate_event_stream",
}


def __getattr__(name: str):
    """Load native-backed exports only when a caller asks for one.

    Pure-Python discovery and neural-ranking tools therefore remain usable
    from a source checkout before the optional PyO3 extension is built.
    """

    if name in _LAZY_NATIVE_EXPORTS:
        module = import_module("._native", __name__)
        value = getattr(module, _LAZY_NATIVE_EXPORTS[name])
        globals()[name] = value
        return value
    if name in _LAZY_CHESS_EXPORTS:
        module = import_module(".chess_adapter", __name__)
        value = getattr(module, _LAZY_CHESS_EXPORTS[name])
        globals()[name] = value
        return value
    if name in _LAZY_EVENT_EXPORTS:
        module = import_module(".events", __name__)
        value = getattr(module, _LAZY_EVENT_EXPORTS[name])
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CHESS_ADAPTER_DOMAIN_ID",
    "CHESS_ADAPTER_PROJECTION_DOMAIN_ID",
    "CHESS_ADAPTER_PROJECTION_RULE",
    "CHESS_ADAPTER_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "FIXED_VALUE_CANDIDATE_SCHEMA_VERSION",
    "FIXED_VALUE_CERTIFICATE_SCHEMA_VERSION",
    "FIXED_VALUE_REPERTOIRE_SCHEMA_VERSION",
    "FIXED_VALUE_TARGET_SCHEMA_VERSION",
    "GENERATION_RECEIPT_SCHEMA_VERSION",
    "POOL_SCHEMA_VERSION",
    "POOL_SCHEMA_VERSION_V2",
    "PROPOSAL_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "RUN_SCHEMA_VERSION",
    "TARGET_SCHEMA_VERSION",
    "VALUE_RULE",
    "LiteralGameStats",
    "ShortGameComparison",
    "adapt_chess_position",
    "analyze_subsystems",
    "build_event_stream",
    "build_ranker_input",
    "build_repertoire",
    "candidate_state_key_for",
    "canonical_event_bytes",
    "canonical_json_bytes",
    "canonical_jsonl_bytes",
    "canonicalize_literal_game",
    "chess_adapter_id_for",
    "compare_repertoire_entries",
    "compare_short_games",
    "evaluate_position",
    "fen_file_reflection_orbit_sha256",
    "find_locked_pawns",
    "fixed_value_candidate_from_chess_adapter",
    "fixed_value_candidate_id_for",
    "fixed_value_target_from_chess_adapter",
    "fixed_value_target_id_for",
    "generate_fixed_value_candidates",
    "generation_receipt_id_for",
    "inspect_repertoire",
    "literal_game_sha256",
    "make_fixed_value_candidate",
    "make_fixed_value_target",
    "partizan_pool_features_for_fen",
    "representation_sha256",
    "replay_chess_witness",
    "validate_candidate_pool_manifest",
    "validate_candidate_proposal",
    "validate_chess_adapter_record",
    "validate_discovery_bundle",
    "validate_discovery_run",
    "validate_event_stream",
    "validate_fixed_value_candidate",
    "validate_fixed_value_target",
    "validate_generation_receipt",
    "validate_repertoire",
    "validate_target_spec",
    "validate_verifier_result",
]
__version__ = "0.1.0"
