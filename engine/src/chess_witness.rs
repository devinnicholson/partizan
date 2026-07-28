//! Deterministic replay for curated orthodox-chess witness lines.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use shakmaty::fen::Fen;
use shakmaty::san::SanPlus;
use shakmaty::uci::UciMove;
use shakmaty::{CastlingMode, Color, EnPassantMode, Position};
use std::str::FromStr;

pub(crate) const WITNESS_VERSION: &str = "partizan.chess_witness.native.v0.1";

fn position_fen(position: &shakmaty::Chess) -> String {
    Fen::from_position(position.clone(), EnPassantMode::Legal).to_string()
}

fn position_state<'py>(
    py: Python<'py>,
    position: &shakmaty::Chess,
) -> PyResult<Bound<'py, PyDict>> {
    let state = PyDict::new(py);
    state.set_item("fen", position_fen(position))?;
    state.set_item(
        "turn",
        if position.turn() == Color::White {
            "white"
        } else {
            "black"
        },
    )?;
    state.set_item("in_check", position.is_check())?;
    state.set_item("checkmate", position.is_checkmate())?;
    state.set_item("stalemate", position.is_stalemate())?;
    state.set_item("legal_move_count", position.legal_moves().len())?;
    Ok(state)
}

/// Replay a complete, explicitly supplied orthodox-chess move witness.
///
/// This function proves only that every UCI move is legal from the preceding
/// state and that the emitted frames reproduce deterministically. It does not
/// prove that the line is forced, optimal, or exhaustive.
#[pyfunction]
pub(crate) fn replay_chess_witness(
    py: Python<'_>,
    fen_str: String,
    uci_moves: Vec<String>,
) -> PyResult<Py<PyDict>> {
    let fen = Fen::from_str(&fen_str)
        .map_err(|error| PyValueError::new_err(format!("Invalid FEN: {error}")))?;
    let mut position: shakmaty::Chess = fen
        .into_position(CastlingMode::Standard)
        .map_err(|error| PyValueError::new_err(format!("Illegal position: {error}")))?;

    let result = PyDict::new(py);
    result.set_item("native_witness_version", WITNESS_VERSION)?;
    result.set_item("input_fen", &fen_str)?;
    result.set_item("canonical_input_fen", position_fen(&position))?;
    result.set_item("move_count", uci_moves.len())?;

    let frames = PyList::empty(py);
    let initial = position_state(py, &position)?;
    initial.set_item("ply", 0)?;
    initial.set_item("move_uci", py.None())?;
    initial.set_item("move_san", py.None())?;
    initial.set_item("move_display", py.None())?;
    initial.set_item("capture", false)?;
    initial.set_item("promotion", false)?;
    frames.append(initial)?;

    for (index, uci_text) in uci_moves.iter().enumerate() {
        let uci = UciMove::from_str(uci_text).map_err(|error| {
            PyValueError::new_err(format!(
                "Invalid UCI move at ply {} ({uci_text}): {error}",
                index + 1
            ))
        })?;
        let chess_move = uci.to_move(&position).map_err(|error| {
            PyValueError::new_err(format!(
                "Illegal UCI move at ply {} ({uci_text}): {error}",
                index + 1
            ))
        })?;
        let san = SanPlus::from_move(position.clone(), &chess_move).to_string();
        let display = chess_move.to_string();
        let capture = chess_move.is_capture();
        let promotion = chess_move.is_promotion();
        position = position.play(&chess_move).map_err(|error| {
            PyValueError::new_err(format!(
                "Could not play move at ply {} ({uci_text}): {error}",
                index + 1
            ))
        })?;

        let frame = position_state(py, &position)?;
        frame.set_item("ply", index + 1)?;
        frame.set_item("move_uci", uci_text)?;
        frame.set_item("move_san", san)?;
        frame.set_item("move_display", display)?;
        frame.set_item("capture", capture)?;
        frame.set_item("promotion", promotion)?;
        frames.append(frame)?;
    }
    result.set_item("frames", frames)?;
    Ok(result.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn elkies_line_replays_to_the_mutual_zugzwang_kernel() {
        Python::initialize();
        Python::attach(|py| {
            let record = replay_chess_witness(
                py,
                "5Q2/5P1b/8/7K/8/1q4k1/1p4B1/8 w - - 0 1".to_owned(),
                [
                    "f8g7", "g3h2", "f7f8q", "b3b5", "h5h6", "b5b6", "g2c6", "b6c6", "h6h7",
                    "b2b1q", "h7h8", "h2h1", "f8g8",
                ]
                .into_iter()
                .map(str::to_owned)
                .collect(),
            )
            .expect("historical line is legal");
            let record = record.bind(py);
            let frames = record
                .get_item("frames")
                .expect("frames lookup succeeds")
                .expect("frames are present")
                .cast_into::<PyList>()
                .expect("frames are a list");
            assert_eq!(frames.len(), 14);
            let final_frame = frames
                .get_item(13)
                .expect("final frame is present")
                .cast_into::<PyDict>()
                .expect("frame is a dict");
            assert_eq!(
                final_frame
                    .get_item("fen")
                    .expect("fen lookup succeeds")
                    .expect("fen is present")
                    .extract::<String>()
                    .expect("fen is a string"),
                "6QK/6Q1/2q5/8/8/8/8/1q5k b - - 3 7"
            );
            assert_eq!(
                final_frame
                    .get_item("move_san")
                    .expect("move lookup succeeds")
                    .expect("move is present")
                    .extract::<String>()
                    .expect("move is a string"),
                "Qfg8"
            );
        });
    }
}
