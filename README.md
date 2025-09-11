# ttmm: Time‑to‑Mental‑Model

`ttmm` is a local‑first code reading assistant designed to reduce the time it takes to load a mental model of a codebase.  It provides static indexing, simple call graph navigation, hotspot detection and dynamic tracing.  You can use it either from the command line or through a Streamlit web UI.

**New**: `ttmm` now supports remote repositories via Git URLs and GitIngest integration, making it easy to analyze any public Python repository without cloning manually.

## Key features (Phase A)

* **Index your repository** – builds a lightweight SQLite database of all Python functions/methods, their definitions, references and coarse call edges using only the standard library.
* **Remote repository support** – analyze any GitHub, GitLab, or Bitbucket repository directly via URL or GitIngest links without manual cloning.
* **Hotspot detection** – computes a hotspot score by combining cyclomatic complexity and recent git churn to help you prioritise where to read first.
* **Static call graph navigation** – shows callers and callees for any symbol using conservative AST analysis.  Attribute calls that cannot be resolved are marked as `<unresolved>`.
* **Keyword search** – a tiny TF‑IDF engine lets you ask a natural language question and returns a minimal reading set of relevant symbols.
* **Dynamic tracing** – run a module, function or script with `sys.settrace` to capture the actual call sequence executed at runtime and persist it in the database.

## Installation

Requirements:

* Python 3.8 or later (except 3.9.7 due to Streamlit compatibility)
* A `git` executable in your `PATH` if you want churn‑based hotspot scores

Install from PyPI:

```bash
pip install zerottmm
```

Or install in development mode from this repository:

```bash
pip install -e .
```

To enable optional extras:

* `[ui]` – install `streamlit` and `openai` for the web UI with AI features
* `[test]` – install `pytest` for running the test suite  
* `[ai]` – install `openai` for AI-enhanced analysis

For example:

```bash
pip install zerottmm[ui,test]
```

## Command line usage

After installation a `zerottmm` command will be available:

```bash
zerottmm index PATH_OR_URL        # index a Python repository (local or remote)
zerottmm hotspots PATH            # show the top hotspots (default 10)
zerottmm callers PATH SYMBOL
zerottmm callees PATH SYMBOL
zerottmm trace PATH [--module pkg.mod:func | --script file.py] [-- args...]
zerottmm answer PATH "your question"
```

* **PATH_OR_URL** – local repository path, Git URL, or GitIngest URL
* **PATH** – local repository path that has been indexed previously
* **SYMBOL** – a fully‑qualified name like `package.module:Class.method` or `package.module:function`.
* **--module** – run a function or module entry point (e.g. `package.module:main`) and trace calls within the repository.
* **--script** – run an arbitrary Python script in the repository and trace calls.

Use `zerottmm --help` for full documentation.

## Examples

Here are some examples analyzing popular Python repositories:

### Analyze the Python requests library
```bash
# Index directly from GitHub
zerottmm index https://github.com/psf/requests.git

# Find hotspots (complex functions with high churn)
zerottmm hotspots /tmp/ttmm_repo_*/
# Output: PreparedRequest.prepare_body, super_len, RequestEncodingMixin._encode_files

# Ask natural language questions  
zerottmm answer /tmp/ttmm_repo_*/ "how to make HTTP requests"
# Output: HTTPAdapter.send, Session.request, HTTPAdapter.cert_verify
```

### Analyze a mathematical optimization library
```bash  
# Index a specialized repo via GitIngest URL
zerottmm index "https://gitingest.com/?url=https://github.com/finite-sample/rank_preserving_calibration"

# Find the main algorithmic components
zerottmm answer /tmp/ttmm_repo_*/ "main calibration algorithm"
# Output: calibrate_dykstra, calibrate_admm, _isotonic_regression

# Explore function relationships
zerottmm callers /tmp/ttmm_repo_*/ "calibrate_dykstra"  
# Shows all the places this core algorithm is used
```

### Analyze FastAPI core (subpath example)
```bash
# Index just the FastAPI core module using GitIngest subpath
zerottmm index "https://gitingest.com/?url=https://github.com/tiangolo/fastapi&subpath=fastapi"

# Find entry points and main interfaces
zerottmm answer /tmp/ttmm_repo_*/ "main application interface"
```

## Streamlit UI

A simple web UI is provided under `app/app.py`.  To run it locally:

```bash
pip install -e .[ui]
streamlit run app/app.py
```

The app allows you to index repositories (local or remote via GitIngest), explore hotspots, get AI-powered insights, and search interactively. Features include:

* **Repository indexing** from local paths, Git URLs, or GitIngest links
* **Automatic repository summary** with key metrics and analysis
* **AI-enhanced analysis** with OpenAI integration (optional)
* **Hotspot detection** and complexity analysis
* **Natural language search** over code symbols

The app is designed to run on [Streamlit Community Cloud](https://streamlit.io/cloud) – simply push this repository to GitHub and deploy the app by pointing to `app/app.py`. The `requirements.txt` file ensures all dependencies (including OpenAI) are automatically installed.

## Development & tests

Tests live in `tests/test_ttmm.py` and cover indexing, hotspot scoring and search.  To run them:

```bash
pip install -e .[test]
pytest -q
```

Continuous integration is configured via `.github/workflows/ci.yml` to run the test suite on Python 3.8 through 3.12.  If you fork this repository on GitHub the workflow will execute automatically.

## Limitations

* Phase A supports Python only and uses conservative static analysis.  Many dynamic method calls cannot be resolved statically; these appear as `<unresolved>` in the call graph.
* Hotspot scores require `git` to compute churn – if `git` is not installed or the directory is not a git repository, churn is assumed to be zero.
* Dynamic tracing only captures calls within the repository root.  Calls to the standard library or external packages are ignored.

Future phases (not implemented here) would add richer language support, deeper type‑aware call resolution and integration with your editor.
