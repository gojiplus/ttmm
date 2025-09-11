"""Repository indexer for ttmm.

The indexer walks a Python repository, parses functions and methods with
``ast`` and stores them in the ttmm database via :mod:`ttmm.store`.
It computes cyclomatic complexity and lines of code for each symbol via
:mod:`ttmm.metrics`, and merges in git churn information via
:mod:`ttmm.gitutils` to produce a hotspot score later on.

Only top‑level functions and class methods are indexed.  Nested
functions are ignored to keep the mental model focused on API surfaces.
Calls made within functions are collected, but attribute calls that
cannot be resolved statically are marked as unresolved.

Example usage:

```
from ttmm.index import index_repo
index_repo("/path/to/repo")
```
"""

from __future__ import annotations

import ast
import os
from typing import Dict, List, Tuple

from . import metrics, gitutils, store


def _iter_python_files(repo_path: str) -> List[str]:
    """Recursively find all Python files in a repository.

    Ignores the ``.ttmm`` directory.  Returns relative paths with
    forward slashes.
    """
    py_files: List[str] = []
    for root, dirs, files in os.walk(repo_path):
        # Skip .ttmm directory
        rel_root = os.path.relpath(root, repo_path)
        if rel_root.startswith(os.path.join(".ttmm")):
            continue
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("."):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, repo_path).replace(os.sep, "/")
                py_files.append(rel_path)
    return py_files


def index_repo(repo_path: str) -> None:
    """Index a Python repository into the ttmm database.

    This will parse all ``.py`` files under ``repo_path``, compute
    symbol definitions, call edges and metrics, and persist them in
    ``.ttmm/ttmm.db``.  Any existing static data in the database is
    replaced.  Dynamic trace data is preserved.
    """
    repo_path = os.path.abspath(repo_path)
    # Discover python files
    py_files = _iter_python_files(repo_path)
    # Compute git churn for all files
    churn_by_file = gitutils.compute_churn(repo_path)
    files_data: List[Tuple[str, float]] = []
    symbols_data: List[Dict[str, object]] = []
    calls_data: List[Dict[str, object]] = []
    metrics_data: Dict[str, Tuple[float, int, float]] = {}
    for rel_path in py_files:
        abs_path = os.path.join(repo_path, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            # Skip unreadable files
            continue
        try:
            tree = ast.parse(source, filename=abs_path)
        except SyntaxError:
            # Skip files with syntax errors
            continue
        mtime = os.path.getmtime(abs_path)
        files_data.append((rel_path, mtime))
        module_name = rel_path[:-3].replace("/", ".")  # strip .py

        class IndexVisitor(ast.NodeVisitor):
            """Visitor to collect top‑level functions and methods and their calls."""

            def __init__(self) -> None:
                self.class_stack: List[str] = []
                self.func_depth = 0  # track nesting of functions

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                # Index only functions not nested inside another function (func_depth == 0)
                if self.func_depth == 0:
                    qualname = module_name + ":" + (
                        f"{self.class_stack[-1]}." if self.class_stack else ""
                    ) + node.name
                    sym_type = "method" if self.class_stack else "function"
                    doc = ast.get_docstring(node)
                    symbols_data.append(
                        {
                            "qualname": qualname,
                            "path": rel_path,
                            "lineno": node.lineno,
                            "endlineno": getattr(node, "end_lineno", node.lineno),
                            "type": sym_type,
                            "doc": doc.strip() if isinstance(doc, str) else None,
                        }
                    )
                    # Metrics
                    comp = metrics.compute_complexity(node)
                    loc = metrics.compute_loc(node)
                    churn = churn_by_file.get(rel_path, 0.0)
                    metrics_data[qualname] = (comp, loc, churn)
                    # Collect calls

                    class CallVisitor(ast.NodeVisitor):
                        def visit_Call(self, call: ast.Call) -> None:
                            callee_name: str | None = None
                            unresolved = False
                            func = call.func
                            if isinstance(func, ast.Name):
                                callee_name = func.id
                            elif isinstance(func, ast.Attribute):
                                callee_name = func.attr
                                unresolved = True
                            if callee_name:
                                calls_data.append(
                                    {
                                        "caller_qualname": qualname,
                                        "callee_name": callee_name,
                                        "unresolved": unresolved,
                                    }
                                )
                            # Continue into nested calls
                            self.generic_visit(call)
                    CallVisitor().visit(node)
                # Recurse into the function to handle nested functions' bodies but not index them
                self.func_depth += 1
                self.generic_visit(node)
                self.func_depth -= 1

            # Also handle async functions similarly
            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                # Treat async functions as normal for indexing
                self.visit_FunctionDef(node)  # type: ignore[arg-type]

        IndexVisitor().visit(tree)
    # Insert into DB
    conn = store.connect(repo_path)
    try:
        store.reset_static_tables(conn)
        store.insert_static_data(conn, files_data, symbols_data, calls_data, metrics_data)
    finally:
        store.close(conn)
