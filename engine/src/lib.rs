use pyo3::prelude::*;

/// A simple function exposed to Python.
#[pyfunction]
fn process_fen(fen: String) -> PyResult<String> {
    Ok(format!("Modified: {}", fen))
}

/// A Python module implemented in Rust.
#[pymodule]
fn partizan(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_fen, m)?)?;
    Ok(())
}
