use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyDict;
use shakmaty::{Chess, Position};
use shakmaty::fen::Fen;
use std::str::FromStr;

use bitmesh::partition_board;
use thermograph::CGTValue;
use astralbase::{RetrogradeEngine, GameValue};

mod decomposer;

#[pyfunction]
fn find_locked_pawns(fen_str: String) -> PyResult<Vec<String>> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen.into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;
    
    let board = pos.board();
    let locked = decomposer::get_locked_pawns(board);
    
    let mut locked_squares = Vec::new();
    for sq in locked {
        locked_squares.push(sq.to_string());
    }
    
    Ok(locked_squares)
}

#[pyfunction]
fn analyze_subsystems(fen_str: String) -> PyResult<(bool, u8)> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen.into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;
    
    let board = pos.board();
    let (is_decomposable, num_components) = decomposer::find_subsystems(board);
    
    Ok((is_decomposable, num_components))
}

#[pyfunction]
fn evaluate_position(py: Python<'_>, fen_str: String) -> PyResult<Py<PyDict>> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|e| PyValueError::new_err(format!("Invalid FEN: {}", e)))?;
    let pos: Chess = fen.into_position(shakmaty::CastlingMode::Standard)
        .map_err(|_| PyValueError::new_err("Could not parse position from FEN"))?;
    
    let board = pos.board();
    
    // 1. BitMesh hook
    let barrier = decomposer::get_locked_pawns(board);
    let mut uf = partition_board(barrier);
    let mut active_components = std::collections::HashSet::new();
    for sq in board.occupied() & !barrier {
        active_components.insert(uf.find(usize::from(sq)));
    }
    let num_components = active_components.len();

    // 2. Thermograph hook
    let therm = CGTValue::Integer(1);
    let (temperature, mean_value) = therm.thermograph();

    // 3. AstralBase hook
    let mut engine = RetrogradeEngine::new();
    engine.add_terminal(pos.clone(), GameValue::Loss(0));
    let expanded_nodes = engine.solve(50);
    
    let dict = PyDict::new(py);
    dict.set_item("components", num_components)?;
    dict.set_item("temperature", temperature)?;
    dict.set_item("mean_value", mean_value)?;
    dict.set_item("expanded_nodes", expanded_nodes)?;
    
    Ok(dict.into())
}

#[pymodule]
fn partizan(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_locked_pawns, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_subsystems, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_position, m)?)?;
    Ok(())
}
