"""Top‑level package for ttmm.

`ttmm` (Time‑to‑Mental‑Model) helps you build a mental model of a Python codebase
faster.  It can index a repository, compute hotspots, navigate static call graphs,
run dynamic traces and answer natural language questions about your code.  The core
functionality lives in submodules:

* `ttmm.index` – parse and index a Python repository
* `ttmm.store` – SQLite persistence layer
* `ttmm.metrics` – compute cyclomatic complexity and other metrics
* `ttmm.gitutils` – git churn calculations
* `ttmm.trace` – runtime tracing using `sys.settrace`
* `ttmm.search` – tiny TF‑IDF search over your codebase
* `ttmm.cli` – command line entry point

Importing this package will expose the `__version__` attribute.  For most use cases
you should call into `ttmm.cli` via the `ttmm` command line, or import functions
from the specific submodules.
"""

from importlib.metadata import version, PackageNotFoundError

try:  # pragma: no cover - during development version metadata may be missing
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "index",
    "store",
    "metrics",
    "gitutils",
    "trace",
    "search",
    "gitingest",
    "ai_analysis",
    "cli",
]
