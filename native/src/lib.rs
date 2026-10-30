mod errors;
mod launcher;
mod login;
use pyo3::prelude::*;

#[pyfunction]
fn launch(py: Python<'_>, path: String, server: String, region: String) -> PyResult<u32> {
    py.allow_threads(|| launcher::launch_game(&path, &server, false, &region)).map_err(Into::into)
}

#[pyfunction(name = "windows")]
fn list_windows() -> Vec<(isize, u32)> {
    launcher::get_wizard_handles().into_iter().map(|h| (h, launcher::get_window_pid(h))).collect()
}

#[pyfunction(name = "login")]
fn login_py(py: Python<'_>, hwnd: isize, username: String, password: String) -> PyResult<()> {
    if username.contains(['\n', '\r', '\0']) || password.contains(['\n', '\r', '\0']) {
        return Err(pyo3::exceptions::PyValueError::new_err("Unsupported control character in credentials"));
    }
    py.allow_threads(|| login::login_to_instance(hwnd, &username, &password)).map_err(Into::into)
}

#[pymodule]
fn wizq_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(launch, m)?)?;
    m.add_function(wrap_pyfunction!(list_windows, m)?)?;
    m.add_function(wrap_pyfunction!(login_py, m)?)?;
    Ok(())
}
