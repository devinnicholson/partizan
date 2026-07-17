"""Narrow Python interface to the Partizan constrained-research engine."""

from ._native import analyze_subsystems, evaluate_position, find_locked_pawns
from .events import (
    EVENT_SCHEMA_VERSION,
    build_event_stream,
    canonical_event_bytes,
    validate_event_stream,
)

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "analyze_subsystems",
    "build_event_stream",
    "canonical_event_bytes",
    "evaluate_position",
    "find_locked_pawns",
    "validate_event_stream",
]
__version__ = "0.1.0"
