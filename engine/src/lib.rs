//! Native Python bindings for Partizan's narrowly scoped research hooks.
//!
//! These functions expose conservative structural observations and a terminal
//! position smoke evaluation. They do not prove full game-tree decomposition,
//! learned agency, chess temperature, or model-guided discovery.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use shakmaty::fen::Fen;
use shakmaty::{Chess, Position};
use std::str::FromStr;

use astralbase::{GameValue, RetrogradeEngine};
use bitmesh::{find_subsystems, get_locked_pawns};
use thermograph::CGTValue;

fn terminal_game_value(pos: &Chess) -> Option<GameValue> {
    if pos.is_checkmate() {
        Some(GameValue::Loss(0))
    } else if pos.is_stalemate() {
        Some(GameValue::Unknown)
    } else {
        None
    }
}

fn thermograph_seed(value: GameValue) -> CGTValue {
    match value {
        GameValue::Win(_) => CGTValue::Integer(1),
        GameValue::Loss(_) => CGTValue::Integer(-1),
        GameValue::Unknown => CGTValue::Integer(0),
    }
}

#[pyfunction]
/// Return squares occupied by pawns in the current locked-pawn screen.
fn find_locked_pawns(fen_str: String) -> PyResult<Vec<String>> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen
        .into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;

    let board = pos.board();
    let locked = get_locked_pawns(board);

    let mut locked_squares = Vec::new();
    for sq in locked {
        locked_squares.push(sq.to_string());
    }

    Ok(locked_squares)
}

#[pyfunction]
/// Return Bitmesh's conservative structural partition observation.
///
/// A positive result is not a theorem that the regions remain independent
/// throughout all future play.
fn analyze_subsystems(fen_str: String) -> PyResult<(bool, u8)> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen
        .into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;

    let board = pos.board();
    let (is_decomposable, num_components) = find_subsystems(board);

    Ok((is_decomposable, num_components))
}

#[pyfunction]
/// Evaluate only a terminal checkmate or stalemate FEN through the three hooks.
///
/// The returned thermograph fields describe a terminal scalar seed used for a
/// plumbing smoke test. They are not evidence of chess temperature.
fn evaluate_position(py: Python<'_>, fen_str: String) -> PyResult<Py<PyDict>> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen
        .into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;

    let board = pos.board();

    let terminal_value = terminal_game_value(&pos).ok_or_else(|| {
        PyValueError::new_err(
            "evaluate_position currently supports only terminal checkmate/stalemate FENs",
        )
    })?;

    // 1. BitMesh hook
    let (_, num_components) = find_subsystems(board);

    // 2. Thermograph hook
    let therm = thermograph_seed(terminal_value);
    let (temperature, mean_value) = therm.thermograph();

    // 3. AstralBase hook
    let mut engine = RetrogradeEngine::new();
    engine.add_terminal(pos.clone(), terminal_value);
    let expanded_nodes = engine.solve(50);

    let dict = PyDict::new(py);
    dict.set_item("components", num_components)?;
    dict.set_item("temperature", temperature)?;
    dict.set_item("mean_value", mean_value)?;
    dict.set_item("expanded_nodes", expanded_nodes)?;

    Ok(dict.into())
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_locked_pawns, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_subsystems, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_position, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use shakmaty::CastlingMode;

    fn parse(fen: &str) -> Chess {
        Fen::from_str(fen)
            .unwrap()
            .into_position(CastlingMode::Standard)
            .unwrap()
    }

    #[test]
    fn terminal_value_rejects_non_terminal_positions() {
        let pos = parse("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");

        assert_eq!(terminal_game_value(&pos), None);
    }

    #[test]
    fn terminal_value_accepts_checkmate() {
        let pos = parse("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3");

        assert_eq!(terminal_game_value(&pos), Some(GameValue::Loss(0)));
    }
}
