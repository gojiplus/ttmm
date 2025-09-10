# ttmm: Time‑to‑Mental‑Model (TTMM)

`ttmm` is a local‑first code reading assistant designed to reduce the time it takes to load a mental model of a codebase.  It provides static indexing, simple call graph navigation, hotspot detection and dynamic tracing.  You can use it either from the command line or through a Streamlit web UI.

## Key features (Phase A)

* **Index your repository** – builds a lightweight SQLite database of all Python functions/methods, their definitions, references and coarse call edges using only the standard library.
* **Hotspot detection** – computes a hotspot score by combining cyclomatic complexity and recent git churn to help you prioritise where to read first.
* **Static call graph navigation** – shows callers and callees for any symbol using conservative AST analysis.  Attribute calls that cannot be resolved are marked as `<unresolved>`.
* **Keyword search** – a tiny TF‑IDF engine lets you ask a natural language question and returns a minimal reading set of relevant symbols.
* **Dynamic tracing** – run a module, function or script with `sys.settrace` to capture the actual call sequence executed at runtime and persist it in the database.

## Installation

Requirements:

* Python 3.9 or later
* A `git` executable in your `PATH` if you want churn‑based hotspot scores

Install the package in editable mode from this repository:

```bash
pip install -e .
```

To enable optional extras:

* `.[ui]` – install `streamlit` for the web UI
* `.[test]` – install `pytest` for running the test suite

For example:

```bash
pip install -e .[ui,test]
```

## Command line usage

After installation a `ttmm` command will be available:

```bash
ttmm index PATH        # index a Python repository
ttmm hotspots PATH     # show the top hotspots (default 10)
ttmm callers PATH SYMBOL
ttmm callees PATH SYMBOL
ttmm trace PATH [--module pkg.mod:func | --script file.py] [-- args...]
ttmm answer PATH "your question"
```

* **PATH** – either the root of a git repository or any folder containing Python code.  A `.ttmm` directory will be created inside with the database.
* **SYMBOL** – a fully‑qualified name like `package.module:Class.method` or `package.module:function`.
* **--module** – run a function or module entry point (e.g. `package.module:main`) and trace calls within the repository.
* **--script** – run an arbitrary Python script in the repository and trace calls.

Use `ttmm --help` for full documentation.

## Streamlit UI

A simple web UI is provided under `app/app.py`.  To run it locally:

```bash
pip install -e .[ui]
streamlit run app/app.py
```

The app allows you to index a repository, explore hotspots, ask a question and see the call graph interactively.  It is designed to run on [Streamlit Community Cloud](https://streamlit.io/cloud) – simply push this repository to GitHub and deploy the app by pointing to `app/app.py`.

## Development & tests

Tests live in `tests/test_ttmm.py` and cover indexing, hotspot scoring and search.  To run them:

```bash
pip install -e .[test]
pytest -q
```

Continuous integration is configured via `.github/workflows/ci.yml` to run the test suite on Python 3.9 through 3.12.  If you fork this repository on GitHub the workflow will execute automatically.

## Limitations

* Phase A supports Python only and uses conservative static analysis.  Many dynamic method calls cannot be resolved statically; these appear as `<unresolved>` in the call graph.
* Hotspot scores require `git` to compute churn – if `git` is not installed or the directory is not a git repository, churn is assumed to be zero.
* Dynamic tracing only captures calls within the repository root.  Calls to the standard library or external packages are ignored.

Future phases (not implemented here) would add richer language support, deeper type‑aware call resolution and integration with your editor.
