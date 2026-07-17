# Partizan native extension

This Cargo package builds the `_native` module inside the `partizan` Python
package. Install it from the repository root through Maturin; the public scope,
quickstart, and claim boundaries are documented in the root `README.md`.

The crate is not independently published. Its upstream dependencies are
versioned at `0.1.0`; local release-candidate testing uses uncommitted Cargo
registry patches as described in `docs/development.md`.
