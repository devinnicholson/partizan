# Distribution boundary

The `partizan-cgt` distribution supports the installed `partizan` package and
the console commands declared in `pyproject.toml`. This includes exact bounded
short-game operations, the bounded chess adapter, event validation, discovery
contract validation, and the two neural ranker interfaces.

The source distribution carries the public contract documents, adapter
schemas, small conformance fixtures, and focused tests needed to inspect these
surfaces. Release CI builds that archive, checks its inventory, installs it,
and runs the installed-package smoke tests.

The Wave 69-R structural-supply and Gate-S programs are repository research
workflows. They require a clean Partizan checkout, sibling dependency
repositories, commit-bound research inputs, `engine/orchestrator.py`, and the
standalone `engine/gate_s_checker` Cargo project. Their Python implementation
modules may be visible in a source archive because they share the package
namespace, but they are outside the installed command and compatibility
surface. Run them only from a checkout following the corresponding frozen
protocol and artifact instructions.

Published wheels do not promise to contain repository research outputs,
historical experiment banks, the visualizer, or paper sources. Those materials
remain independently archived and content-addressed under the repository's
artifact policy.
