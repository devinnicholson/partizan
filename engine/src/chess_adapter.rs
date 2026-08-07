//! Bounded chess-to-short-game projection for the Python release surface.

use astralbase::domain::{
    DecompositionGateRejection, DecompositionGateStatus, DomainRejectionCode, TerminalStatus,
    ValidatedDomainPosition, validate_first_constrained_fen,
};
use bitmesh::certify_conservative_legal_independence;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use shakmaty::fen::Fen;
use shakmaty::{Color, EnPassantMode, Position};
use thermograph::CGTValue;

pub(crate) const ADAPTER_VERSION: &str = "partizan.bounded_chess_adapter.native.v0.2";
pub(crate) const PROJECTION_DOMAIN_ID: &str = "formal_domain:bounded_chess_projection:v0";
pub(crate) const PROJECTION_RULE: &str = "bounded_alternating_legal_move_normal_play_v1";
const MAX_PLIES: i64 = 8;
const MAX_NODE_BUDGET: i64 = 100_000;
const ASTRALBASE_SOURCE_COMMIT: &str = "0e36d14b78a7a4915689e510bff6d7c0f20152e4";
const BITMESH_SOURCE_COMMIT: &str = "410550c0964004cd7ba9677539f17ae82c139dd8";
const THERMOGRAPH_SOURCE_COMMIT: &str = "32d6bfbc966f47a87e7249d4ed8818370288e079";

#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct ProjectionStats {
    visited_position_nodes: u64,
    legal_edges: u64,
    duplicate_literal_options_removed: u64,
    horizon_leaves: u64,
    checkmate_leaves: u64,
    stalemate_leaves: u64,
    max_depth_reached: u8,
}

#[derive(Debug)]
enum ProjectionError {
    NodeBudgetExhausted,
    PositionTransitionFailed(String),
}

fn empty_game() -> CGTValue {
    CGTValue::GameTree {
        left: Vec::new(),
        right: Vec::new(),
    }
}

fn deduplicate_options(options: Vec<CGTValue>, stats: &mut ProjectionStats) -> Vec<CGTValue> {
    let original_len = options.len();
    let mut keyed_options = options
        .into_iter()
        .map(|option| (option.canonical_serialization(), option))
        .collect::<Vec<_>>();
    keyed_options.sort_by(|left, right| left.0.cmp(&right.0));
    keyed_options.dedup_by(|left, right| left.0 == right.0);
    stats.duplicate_literal_options_removed +=
        u64::try_from(original_len - keyed_options.len()).unwrap_or(u64::MAX);
    keyed_options
        .into_iter()
        .map(|(_, option)| option)
        .collect()
}

fn project_position(
    position: &shakmaty::Chess,
    depth: u8,
    max_plies: u8,
    node_budget: u64,
    stats: &mut ProjectionStats,
) -> Result<CGTValue, ProjectionError> {
    if stats.visited_position_nodes >= node_budget {
        return Err(ProjectionError::NodeBudgetExhausted);
    }
    stats.visited_position_nodes += 1;
    stats.max_depth_reached = stats.max_depth_reached.max(depth);

    let legal_moves = position.legal_moves();
    if legal_moves.is_empty() {
        if position.is_check() {
            stats.checkmate_leaves += 1;
        } else {
            stats.stalemate_leaves += 1;
        }
        return Ok(empty_game());
    }
    if depth == max_plies {
        stats.horizon_leaves += 1;
        return Ok(empty_game());
    }

    let mut ordered_moves = legal_moves
        .iter()
        .map(|chess_move| (chess_move.to_string(), chess_move.clone()))
        .collect::<Vec<_>>();
    ordered_moves.sort_by(|left, right| left.0.cmp(&right.0));
    stats.legal_edges += u64::try_from(ordered_moves.len()).unwrap_or(u64::MAX);

    let mut options = Vec::with_capacity(ordered_moves.len());
    for (_, chess_move) in ordered_moves {
        let child = position.clone().play(&chess_move).map_err(|error| {
            ProjectionError::PositionTransitionFailed(format!("{chess_move}: {error}"))
        })?;
        options.push(project_position(
            &child,
            depth + 1,
            max_plies,
            node_budget,
            stats,
        )?);
    }
    let options = deduplicate_options(options, stats);

    Ok(if position.turn() == Color::White {
        CGTValue::GameTree {
            left: options,
            right: Vec::new(),
        }
    } else {
        CGTValue::GameTree {
            left: Vec::new(),
            right: options,
        }
    })
}

fn literal_node_count(value: &CGTValue) -> u64 {
    let (left, right) = value.options();
    1 + left
        .iter()
        .chain(right.iter())
        .map(literal_node_count)
        .sum::<u64>()
}

fn game_to_python(py: Python<'_>, value: &CGTValue) -> PyResult<Py<PyDict>> {
    let (left, right) = value.options();
    let left_values = PyList::empty(py);
    for option in &left {
        left_values.append(game_to_python(py, option)?)?;
    }
    let right_values = PyList::empty(py);
    for option in &right {
        right_values.append(game_to_python(py, option)?)?;
    }

    let game = PyDict::new(py);
    game.set_item("left", left_values)?;
    game.set_item("right", right_values)?;
    Ok(game.into())
}

fn settings_dict(py: Python<'_>, max_plies: i64, node_budget: i64) -> PyResult<Py<PyDict>> {
    let settings = PyDict::new(py);
    settings.set_item("max_plies", max_plies)?;
    settings.set_item("node_budget", node_budget)?;
    Ok(settings.into())
}

fn refusal_dict(
    py: Python<'_>,
    code: &str,
    message: &str,
    details: Option<Vec<String>>,
) -> PyResult<Py<PyDict>> {
    let refusal = PyDict::new(py);
    refusal.set_item("code", code)?;
    refusal.set_item("message", message)?;
    match details {
        Some(details) => refusal.set_item("details", details)?,
        None => refusal.set_item("details", py.None())?,
    }
    Ok(refusal.into())
}

fn base_result<'py>(
    py: Python<'py>,
    fen: &str,
    max_plies: i64,
    node_budget: i64,
) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new(py);
    result.set_item("native_adapter_version", ADAPTER_VERSION)?;
    let upstream_sources = PyDict::new(py);
    for (name, source_commit) in [
        ("astralbase", ASTRALBASE_SOURCE_COMMIT),
        ("bitmesh", BITMESH_SOURCE_COMMIT),
        ("thermograph", THERMOGRAPH_SOURCE_COMMIT),
    ] {
        let source = PyDict::new(py);
        source.set_item("version", "0.1.0")?;
        source.set_item("source_commit", source_commit)?;
        upstream_sources.set_item(name, source)?;
    }
    result.set_item("upstream_sources", upstream_sources)?;
    result.set_item("input", {
        let input = PyDict::new(py);
        input.set_item("encoding", "fen")?;
        input.set_item("fen", fen)?;
        input
    })?;
    result.set_item("settings", settings_dict(py, max_plies, node_budget)?)?;
    Ok(result)
}

fn rejected_settings_result(
    py: Python<'_>,
    fen: &str,
    max_plies: i64,
    node_budget: i64,
    detail: String,
) -> PyResult<Py<PyDict>> {
    let result = base_result(py, fen, max_plies, node_budget)?;
    result.set_item("status", "refused")?;
    result.set_item("domain_gate", py.None())?;
    result.set_item("projection", py.None())?;
    result.set_item(
        "refusal",
        refusal_dict(
            py,
            "invalid_adapter_settings",
            "Adapter settings fall outside the bounded projection contract.",
            Some(vec![detail]),
        )?,
    )?;
    Ok(result.into())
}

fn domain_rejection_code(code: DomainRejectionCode) -> &'static str {
    code.as_str()
}

fn rejected_domain_result(
    py: Python<'_>,
    fen: &str,
    max_plies: i64,
    node_budget: i64,
    report: astralbase::domain::DomainRejectionReport,
) -> PyResult<Py<PyDict>> {
    let result = base_result(py, fen, max_plies, node_budget)?;
    result.set_item("status", "refused")?;

    let reasons = PyList::empty(py);
    for reason in report.reasons() {
        let item = PyDict::new(py);
        item.set_item("code", domain_rejection_code(reason.code))?;
        match &reason.detail {
            Some(detail) => item.set_item("detail", detail)?,
            None => item.set_item("detail", py.None())?,
        }
        reasons.append(item)?;
    }
    let gate = PyDict::new(py);
    gate.set_item("status", "refused")?;
    gate.set_item("domain_id", astralbase::domain::FIRST_CONSTRAINED_DOMAIN_ID)?;
    gate.set_item("canonical_fen", py.None())?;
    gate.set_item("move_state_key", py.None())?;
    gate.set_item("terminal_status", py.None())?;
    gate.set_item("immediate_terminal_tactic", py.None())?;
    gate.set_item("decomposition", py.None())?;
    gate.set_item("reasons", reasons)?;
    result.set_item("domain_gate", gate)?;
    result.set_item("projection", py.None())?;
    result.set_item(
        "refusal",
        refusal_dict(
            py,
            "domain_rejected",
            "The FEN failed the first constrained chess domain.",
            Some(report.reason_messages()),
        )?,
    )?;
    Ok(result.into())
}

fn terminal_name(status: Option<TerminalStatus>) -> Option<&'static str> {
    status.map(TerminalStatus::as_str)
}

fn move_state_key(position: &shakmaty::Chess) -> String {
    Fen::from_position(position.clone(), EnPassantMode::Legal)
        .to_string()
        .split_whitespace()
        .take(4)
        .collect::<Vec<_>>()
        .join(" ")
}

fn decomposition_status_name(status: DecompositionGateStatus) -> &'static str {
    match status {
        DecompositionGateStatus::Strict => "strict",
        DecompositionGateStatus::Rejected(_) => "rejected",
    }
}

fn decomposition_rejection_name(status: DecompositionGateStatus) -> Option<&'static str> {
    match status {
        DecompositionGateStatus::Strict => None,
        DecompositionGateStatus::Rejected(reason) => Some(match reason {
            DecompositionGateRejection::NoLockedBarrier => "no_locked_barrier",
            DecompositionGateRejection::LessThanTwoActiveComponents => {
                "less_than_two_active_components"
            }
            DecompositionGateRejection::InvalidCertificate => "invalid_certificate",
        }),
    }
}

fn accepted_domain_dict(
    py: Python<'_>,
    validated: &ValidatedDomainPosition,
) -> PyResult<Py<PyDict>> {
    let gate = PyDict::new(py);
    gate.set_item("status", "accepted")?;
    gate.set_item("domain_id", astralbase::domain::FIRST_CONSTRAINED_DOMAIN_ID)?;
    gate.set_item(
        "canonical_fen",
        Fen::from_position(validated.position().clone(), EnPassantMode::Legal).to_string(),
    )?;
    gate.set_item("move_state_key", move_state_key(validated.position()))?;
    match terminal_name(validated.terminal_status()) {
        Some(status) => gate.set_item("terminal_status", status)?,
        None => gate.set_item("terminal_status", py.None())?,
    }

    match validated.immediate_terminal_tactic() {
        Some(tactic) => {
            let record = PyDict::new(py);
            record.set_item("legal_move_count", tactic.legal_move_count())?;
            record.set_item("checkmating_moves", tactic.checkmating_moves())?;
            record.set_item("stalemating_moves", tactic.stalemating_moves())?;
            gate.set_item("immediate_terminal_tactic", record)?;
        }
        None => gate.set_item("immediate_terminal_tactic", py.None())?,
    }

    let decomposition = validated.decomposition();
    let decomposition_record = PyDict::new(py);
    decomposition_record.set_item("status", decomposition_status_name(decomposition.status))?;
    decomposition_record.set_item(
        "active_component_count",
        decomposition.active_component_count,
    )?;
    decomposition_record.set_item("digest_sha256", &decomposition.digest)?;
    match decomposition_rejection_name(decomposition.status) {
        Some(reason) => decomposition_record.set_item("rejection_code", reason)?,
        None => decomposition_record.set_item("rejection_code", py.None())?,
    }

    let independence_record = PyDict::new(py);
    match certify_conservative_legal_independence(validated.position().board()) {
        Ok(proof) => {
            independence_record.set_item("status", "certified")?;
            independence_record.set_item("proof_kind", proof.proof_kind)?;
            independence_record.set_item(
                "decomposition_digest_sha256",
                proof.decomposition_digest.to_string(),
            )?;
        }
        Err(_) => {
            independence_record.set_item("status", "unavailable")?;
            independence_record.set_item("proof_kind", py.None())?;
            independence_record.set_item("decomposition_digest_sha256", py.None())?;
        }
    }
    decomposition_record.set_item("conservative_one_ply_independence", independence_record)?;
    gate.set_item("decomposition", decomposition_record)?;
    gate.set_item("reasons", PyList::empty(py))?;
    Ok(gate.into())
}

fn stats_dict(
    py: Python<'_>,
    stats: &ProjectionStats,
    literal_nodes: Option<u64>,
) -> PyResult<Py<PyDict>> {
    let record = PyDict::new(py);
    record.set_item("visited_position_nodes", stats.visited_position_nodes)?;
    record.set_item("legal_edges", stats.legal_edges)?;
    record.set_item(
        "duplicate_literal_options_removed",
        stats.duplicate_literal_options_removed,
    )?;
    record.set_item("horizon_leaves", stats.horizon_leaves)?;
    record.set_item("checkmate_leaves", stats.checkmate_leaves)?;
    record.set_item("stalemate_leaves", stats.stalemate_leaves)?;
    record.set_item("max_depth_reached", stats.max_depth_reached)?;
    match literal_nodes {
        Some(count) => record.set_item("literal_game_nodes", count)?,
        None => record.set_item("literal_game_nodes", py.None())?,
    }
    Ok(record.into())
}

fn projection_dict(
    py: Python<'_>,
    validated: &ValidatedDomainPosition,
    value: &CGTValue,
    stats: &ProjectionStats,
) -> PyResult<Py<PyDict>> {
    let projection = PyDict::new(py);
    projection.set_item("domain_id", PROJECTION_DOMAIN_ID)?;
    projection.set_item("rule", PROJECTION_RULE)?;
    projection.set_item(
        "root_turn",
        if validated.position().turn() == Color::White {
            "white"
        } else {
            "black"
        },
    )?;
    projection.set_item("literal_game", game_to_python(py, value)?)?;
    projection.set_item(
        "statistics",
        stats_dict(py, stats, Some(literal_node_count(value)))?,
    )?;

    let payload = value.exact_value_payload();
    let identity = PyDict::new(py);
    identity.set_item("semantics", "structural_tree_identity_only")?;
    identity.set_item("value_class", payload.value_class.as_str())?;
    identity.set_item("canonical_serialization", payload.canonical_serialization)?;
    identity.set_item("legacy_digest", payload.digest)?;
    identity.set_item("digest_v1_sha256", value.digest_v1_sha256())?;
    match payload.dyadic {
        Some(dyadic) => {
            let dyadic_record = PyDict::new(py);
            dyadic_record.set_item("numerator", dyadic.numerator())?;
            dyadic_record.set_item("denominator_power", dyadic.denominator_power())?;
            identity.set_item("dyadic", dyadic_record)?;
        }
        None => identity.set_item("dyadic", py.None())?,
    }
    projection.set_item("thermograph_identity", identity)?;
    Ok(projection.into())
}

/// Convert one constrained FEN into a finite normal-play option tree.
///
/// White legal moves are Left options, Black legal moves are Right options,
/// and every node at the declared horizon is the zero game. Checkmate and
/// stalemate are also zero leaves under this projection. This is an exact
/// finite game under the named rule. Its certificate is scoped to that
/// derived game.
#[pyfunction]
#[pyo3(signature = (fen_str, max_plies=2, node_budget=10_000))]
pub(crate) fn adapt_chess_position(
    py: Python<'_>,
    fen_str: String,
    max_plies: i64,
    node_budget: i64,
) -> PyResult<Py<PyDict>> {
    if !(1..=MAX_PLIES).contains(&max_plies) {
        return rejected_settings_result(
            py,
            &fen_str,
            max_plies,
            node_budget,
            format!("max_plies must be an integer from 1 through {MAX_PLIES}"),
        );
    }
    if !(1..=MAX_NODE_BUDGET).contains(&node_budget) {
        return rejected_settings_result(
            py,
            &fen_str,
            max_plies,
            node_budget,
            format!("node_budget must be an integer from 1 through {MAX_NODE_BUDGET}"),
        );
    }

    let validated = match validate_first_constrained_fen(&fen_str) {
        Ok(validated) => validated,
        Err(report) => {
            return rejected_domain_result(py, &fen_str, max_plies, node_budget, report);
        }
    };
    let domain_gate = accepted_domain_dict(py, &validated)?;
    let mut stats = ProjectionStats::default();
    let projection = project_position(
        validated.position(),
        0,
        u8::try_from(max_plies).expect("validated max_plies fits u8"),
        u64::try_from(node_budget).expect("validated node_budget fits u64"),
        &mut stats,
    );

    let result = base_result(py, &fen_str, max_plies, node_budget)?;
    result.set_item("domain_gate", domain_gate)?;
    match projection {
        Ok(value) => {
            result.set_item("status", "accepted")?;
            result.set_item(
                "projection",
                projection_dict(py, &validated, &value, &stats)?,
            )?;
            result.set_item("refusal", py.None())?;
        }
        Err(ProjectionError::NodeBudgetExhausted) => {
            result.set_item("status", "refused")?;
            result.set_item("projection", py.None())?;
            result.set_item(
                "refusal",
                refusal_dict(
                    py,
                    "node_budget_exhausted",
                    "The projection reached its declared position-node budget.",
                    Some(vec![format!(
                        "visited {} position nodes",
                        stats.visited_position_nodes
                    )]),
                )?,
            )?;
        }
        Err(ProjectionError::PositionTransitionFailed(detail)) => {
            result.set_item("status", "refused")?;
            result.set_item("projection", py.None())?;
            result.set_item(
                "refusal",
                refusal_dict(
                    py,
                    "position_transition_failed",
                    "A legal-move transition could not be constructed.",
                    Some(vec![detail]),
                )?,
            )?;
        }
    }
    Ok(result.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use shakmaty::CastlingMode;
    use std::str::FromStr;

    fn parse(fen: &str) -> shakmaty::Chess {
        Fen::from_str(fen)
            .unwrap()
            .into_position(CastlingMode::Standard)
            .unwrap()
    }

    #[test]
    fn terminal_checkmate_projects_to_zero() {
        let position = parse("7k/5KQ1/8/8/8/8/8/8 b - - 0 1");
        let mut stats = ProjectionStats::default();
        let value = project_position(&position, 0, 2, 100, &mut stats).unwrap();

        assert_eq!(value, empty_game());
        assert_eq!(stats.checkmate_leaves, 1);
        assert_eq!(stats.visited_position_nodes, 1);
    }

    #[test]
    fn mate_frontier_is_deterministic_and_deduplicated() {
        let position = parse("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1");
        let mut first_stats = ProjectionStats::default();
        let first = project_position(&position, 0, 1, 100, &mut first_stats).unwrap();
        let mut second_stats = ProjectionStats::default();
        let second = project_position(&position, 0, 1, 100, &mut second_stats).unwrap();

        assert_eq!(first, second);
        assert_eq!(first_stats, second_stats);
        assert_eq!(first_stats.legal_edges, 26);
        assert_eq!(first_stats.checkmate_leaves, 4);
        assert_eq!(first_stats.stalemate_leaves, 10);
        assert_eq!(first_stats.horizon_leaves, 12);
        assert_eq!(first_stats.duplicate_literal_options_removed, 25);
        assert_eq!(literal_node_count(&first), 2);
    }

    #[test]
    fn node_budget_fails_closed() {
        let position = parse("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1");
        let mut stats = ProjectionStats::default();
        let result = project_position(&position, 0, 2, 1, &mut stats);

        assert!(matches!(result, Err(ProjectionError::NodeBudgetExhausted)));
        assert_eq!(stats.visited_position_nodes, 1);
    }
}
