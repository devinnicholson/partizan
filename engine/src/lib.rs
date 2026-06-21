use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use shakmaty::{Chess, Position};
use shakmaty::fen::Fen;
use std::str::FromStr;

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

#[pymodule]
fn partizan(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_locked_pawns, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_subsystems, m)?)?;
    Ok(())
}
