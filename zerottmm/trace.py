"""Runtime tracing for ttmm.

This module provides a function to trace the runtime call graph of a
Python module or script.  It uses ``sys.settrace`` to record every
function call within the indexed repository and persists the edges in
the database under ``trace_runs`` and ``trace_events``.  Trace data is
stored separately from static edges and does not affect index state.

Example usage:

```
from ttmm.trace import run_tracing
run_tracing("./myrepo", module="mypkg.cli:main", args=["--help"])
```
"""

from __future__ import annotations

import importlib
import os
import runpy
import sys
import time
from typing import Dict, List, Optional, Tuple

from . import store


def _build_symbol_intervals(conn, repo_path: str) -> Dict[str, List[Tuple[int, int, int]]]:
    """Build a mapping from file path to sorted intervals for symbol lookup.

    Each entry maps ``relative_path`` to a list of ``(start, end, symbol_id)``
    sorted by descending start.  This allows efficient lookup of the
    innermost containing symbol during tracing.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbols.id AS id, symbols.lineno AS start, symbols.endlineno AS end,
               files.path AS file_path
        FROM symbols
        JOIN files ON files.id = symbols.file_id
        ORDER BY symbols.lineno DESC
        """
    )
    mapping: Dict[str, List[Tuple[int, int, int]]] = {}
    for row in cur.fetchall():
        mapping.setdefault(row["file_path"], []).append((row["start"], row["end"], row["id"]))
    # Sort each list by descending start line for quick first match
    for lst in mapping.values():
        lst.sort(key=lambda t: t[0], reverse=True)
    return mapping


def _lookup_symbol(
    symbol_intervals: Dict[str, List[Tuple[int, int, int]]], rel_path: str, lineno: int
) -> Optional[int]:
    """Return the symbol id containing a given file/line position, or None."""
    intervals = symbol_intervals.get(rel_path)
    if not intervals:
        return None
    for start, end, sid in intervals:
        if start <= lineno <= end:
            return sid
    return None


def run_tracing(
    repo_path: str,
    module: Optional[str] = None,
    script: Optional[str] = None,
    args: Optional[List[str]] = None,
) -> None:
    """Trace execution of a module or script and persist call edges.

    Exactly one of ``module`` or ``script`` must be provided.  The
    function will import and run the target while recording calls
    between functions defined within ``repo_path``.  The trace is
    persisted in the ``trace_runs`` and ``trace_events`` tables.

    Parameters
    ----------
    repo_path: str
        Path to the root of the repository to trace.  Should have been
        indexed previously.
    module: Optional[str]
        A string of the form ``pkg.mod:func`` pointing to an entry
        point to call.  If the part after ``:`` is omitted the module
        itself is executed (its top‑level code runs).
    script: Optional[str]
        Path to a Python script relative to ``repo_path`` to execute.
        Cannot be used together with ``module``.
    args: Optional[List[str]]
        List of arguments to pass to the function or script.  For a
        module function these are passed positionally; for scripts they
        populate ``sys.argv`` starting at index 1.
    """
    if (module is None and script is None) or (module is not None and script is not None):
        raise ValueError("Exactly one of module or script must be specified")
    repo_path = os.path.abspath(repo_path)
    args = args or []
    conn = store.connect(repo_path)
    try:
        symbol_intervals = _build_symbol_intervals(conn, repo_path)
        # Precompute mapping from abs file path -> rel path
        file_map: Dict[str, str] = {}
        for rel_path in symbol_intervals.keys():
            file_map[os.path.abspath(os.path.join(repo_path, rel_path))] = rel_path
        call_pairs: List[Tuple[int, int]] = []

        call_stack: List[Optional[int]] = []

        def tracer(frame, event, arg):
            if event == "call":
                code = frame.f_code
                abs_path = os.path.abspath(code.co_filename)
                rel_path = file_map.get(abs_path)
                if rel_path is not None:
                    lineno = frame.f_lineno
                    callee_id = _lookup_symbol(symbol_intervals, rel_path, lineno)
                    # Determine caller from stack
                    caller_id = call_stack[-1] if call_stack else None
                    if caller_id is not None and callee_id is not None:
                        call_pairs.append((caller_id, callee_id))
                    # Push callee_id (may be None)
                    call_stack.append(callee_id)
                else:
                    # External call: push None to maintain stack depth
                    call_stack.append(None)
                return tracer
            elif event == "return":
                # Pop stack
                if call_stack:
                    call_stack.pop()
                return tracer
            return tracer

        # Prepare to run
        # Save original argv and modules to restore later
        old_argv = sys.argv.copy()
        try:
            sys.settrace(tracer)
            if module:
                if ":" in module:
                    mod_name, func_name = module.split(":", 1)
                    mod = importlib.import_module(mod_name)
                    func = getattr(mod, func_name)
                    # Call with provided args
                    func(*args)
                else:
                    # Import module and run top‑level code
                    importlib.import_module(module)
            else:
                # script
                script_path = os.path.join(repo_path, script)
                sys.argv = [script_path] + args
                runpy.run_path(script_path, run_name="__main__")
        finally:
            sys.settrace(None)
            sys.argv = old_argv
        # Persist run and events
        if call_pairs:
            cur = conn.cursor()
            ts = time.time()
            description = module or script or "trace"
            cur.execute(
                "INSERT INTO trace_runs (ts, description) VALUES (?, ?)",
                (ts, description),
            )
            run_id = cur.lastrowid
            for caller_id, callee_id in call_pairs:
                cur.execute(
                    "INSERT INTO trace_events (run_id, caller_id, callee_id) VALUES (?, ?, ?)",
                    (run_id, caller_id, callee_id),
                )
            conn.commit()
    finally:
        store.close(conn)
