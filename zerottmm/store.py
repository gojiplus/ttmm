"""Persistence layer for ttmm.

This module defines an SQLite schema and helper functions for storing
information about files, symbols, call edges, metrics and trace runs.
The database is stored under ``.ttmm/ttmm.db`` in the repository root.

The tables are:

``files``
    One row per indexed file (Python module).  Stores the relative path and
    modification time.

``symbols``
    One row per function or method.  Holds the file it belongs to, a
    qualified name (``module:Function`` or ``module:Class.method``), the
    line range, a type (``function`` or ``method``) and an optional
    docstring.

``edges``
    Static call edges extracted from AST.  Each row links a caller symbol
    (``caller_id``) to a callee symbol (``callee_id``) or provides the
    unresolved callee name if the call target could not be resolved
    statically.

``metrics``
    Stores per‑symbol metrics such as cyclomatic complexity, lines of code
    and churn.  The final hotspot score should be computed outside this
    module.

``trace_runs`` and ``trace_events``
    Used by ``ttmm.trace`` to record actual runtime call edges.  Each run
    gets an entry in ``trace_runs`` and individual call pairs are stored
    in ``trace_events`` referencing the run.  Dynamic edges use the
    same symbol IDs as static edges; if a symbol is removed and re‑indexed
    the foreign keys will cascade delete the associated dynamic events.

The ``connect`` function creates the database on demand and ensures that
the schema is up to date.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Optional, Tuple


def get_db_path(repo_path: str) -> str:
    """Return the absolute path to the ttmm database for a given repository.

    The database lives in ``.ttmm/ttmm.db`` under the repository root.
    """
    return os.path.join(repo_path, ".ttmm", "ttmm.db")


def connect(repo_path: str) -> sqlite3.Connection:
    """Open a SQLite connection for a repository.

    Ensures that the target directory exists and the schema is created.

    Parameters
    ----------
    repo_path: str
        Absolute or relative path to the repository root.

    Returns
    -------
    sqlite3.Connection
        An open connection with the correct row factory set.
    """
    db_path = get_db_path(repo_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create schema tables if they do not exist."""
    cur = conn.cursor()
    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON")
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            mtime REAL
        );
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            qualname TEXT NOT NULL,
            lineno INTEGER NOT NULL,
            endlineno INTEGER NOT NULL,
            type TEXT NOT NULL,
            doc TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_qualname ON symbols(qualname);
        CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY,
            caller_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
            callee_id INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
            callee_name TEXT,
            unresolved INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_edges_caller ON edges(caller_id);
        CREATE INDEX IF NOT EXISTS idx_edges_callee ON edges(callee_id);
        CREATE TABLE IF NOT EXISTS metrics (
            symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            complexity REAL,
            loc INTEGER,
            churn REAL
        );
        CREATE TABLE IF NOT EXISTS trace_runs (
            id INTEGER PRIMARY KEY,
            ts REAL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS trace_events (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES trace_runs(id) ON DELETE CASCADE,
            caller_id INTEGER,
            callee_id INTEGER
        );
        """
    )
    conn.commit()


def reset_static_tables(conn: sqlite3.Connection) -> None:
    """Remove all static data (files, symbols, edges, metrics).

    Trace tables are left intact.  This is useful when re‑indexing a repository
    from scratch.
    """
    cur = conn.cursor()
    cur.executescript(
        """
        DELETE FROM edges;
        DELETE FROM metrics;
        DELETE FROM symbols;
        DELETE FROM files;
        """
    )
    conn.commit()


def insert_static_data(
    conn: sqlite3.Connection,
    files_data: List[Tuple[str, float]],
    symbols_data: List[Dict[str, object]],
    calls_data: List[Dict[str, object]],
    metrics_data: Dict[str, Tuple[float, int, float]],
) -> None:
    """Insert static analysis results into the database.

    Parameters
    ----------
    conn: sqlite3.Connection
        An open connection with schema prepared.
    files_data: List[Tuple[str, float]]
        List of ``(relative_path, mtime)`` for each Python file indexed.
    symbols_data: List[Dict[str, object]]
        Each entry must contain ``qualname``, ``path`` (relative file path),
        ``lineno``, ``endlineno``, ``type`` and ``doc``.
    calls_data: List[Dict[str, object]]
        Each entry contains ``caller_qualname``, ``callee_name`` and
        ``unresolved`` (boolean indicating an attribute call).  Caller
        qualnames must correspond to entries in ``symbols_data``.
    metrics_data: Dict[str, Tuple[float, int, float]]
        Mapping from symbol qualname to a tuple ``(complexity, loc, churn)``.
    """
    cur = conn.cursor()
    # Insert files and build a map path -> id
    file_ids: Dict[str, int] = {}
    for path, mtime in files_data:
        cur.execute(
            "INSERT OR REPLACE INTO files (path, mtime) VALUES (?, ?)",
            (path, mtime),
        )
    # Load ids
    cur.execute("SELECT id, path FROM files")
    for row in cur.fetchall():
        file_ids[row["path"]] = row["id"]

    # Insert symbols
    for sym in symbols_data:
        file_id = file_ids[sym["path"]]
        cur.execute(
            "INSERT INTO symbols (file_id, qualname, lineno, endlineno, type, doc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                file_id,
                sym["qualname"],
                sym["lineno"],
                sym["endlineno"],
                sym["type"],
                sym.get("doc"),
            ),
        )
    # Build a map from qualname to symbol_id
    cur.execute("SELECT id, qualname FROM symbols")
    sym_map: Dict[str, int] = {}
    for row in cur.fetchall():
        sym_map[row["qualname"]] = row["id"]

    # Insert edges
    for call in calls_data:
        caller_id = sym_map.get(call["caller_qualname"])
        if caller_id is None:
            continue  # skip unknown caller (should not happen)
        callee_name = call["callee_name"]
        # Attempt to resolve callee name among all symbols
        callee_matches = [
            sid for qn, sid in sym_map.items()
            if qn.endswith(":" + callee_name) or qn.split(":")[-1].split(".")[-1] == callee_name
        ]
        callee_id: Optional[int] = None
        unresolved = call.get("unresolved", False)
        if not unresolved and len(callee_matches) == 1:
            callee_id = callee_matches[0]
        else:
            callee_id = None
        cur.execute(
            "INSERT INTO edges (caller_id, callee_id, callee_name, unresolved) VALUES (?, ?, ?, ?)",
            (caller_id, callee_id, callee_name, 1 if callee_id is None else 0),
        )
    # Insert metrics
    for qualname, (complexity, loc, churn) in metrics_data.items():
        sid = sym_map.get(qualname)
        if sid is None:
            continue
        cur.execute(
            "INSERT INTO metrics (symbol_id, complexity, loc, churn) VALUES (?, ?, ?, ?)",
            (sid, complexity, loc, churn),
        )
    conn.commit()


def get_hotspots(conn: sqlite3.Connection, limit: int = 10) -> List[sqlite3.Row]:
    """Return top symbols by hotspot score.

    The hotspot score is defined as ``complexity * (1 + sqrt(churn))`` and
    computed on the fly.  Complexity and churn come from the ``metrics``
    table.  Symbols without metrics are ignored.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbols.qualname AS qualname,
               files.path AS file_path,
               symbols.lineno AS lineno,
               metrics.complexity AS complexity,
               metrics.churn AS churn,
               metrics.loc AS loc
        FROM symbols
        JOIN metrics ON metrics.symbol_id = symbols.id
        JOIN files ON files.id = symbols.file_id
        ORDER BY metrics.complexity DESC, metrics.churn DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def resolve_symbol(conn: sqlite3.Connection, name: str) -> Optional[int]:
    """Resolve a user‑supplied symbol name to an ID.

    The name may be fully qualified (e.g. ``package.module:Class.method``)
    or just a bare name.  If it is fully qualified, an exact match is
    attempted.  Otherwise the function searches for symbols whose
    qualname ends with ``:name`` or ``.<name>``.  If multiple matches
    are found, the one with the highest hotspot score is chosen.  If no
    match is found, ``None`` is returned.
    """
    cur = conn.cursor()
    # Try exact match
    cur.execute("SELECT id FROM symbols WHERE qualname = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Fallback search: match by suffix after colon or dot
    # We need metrics to rank by hotspot score
    cur.execute(
        """
        SELECT symbols.id AS id,
               symbols.qualname AS qualname,
               metrics.complexity AS complexity,
               metrics.churn AS churn
        FROM symbols
        JOIN metrics ON metrics.symbol_id = symbols.id
        WHERE symbols.qualname LIKE '%' || ?
        ORDER BY metrics.complexity DESC, metrics.churn DESC
        """,
        (":" + name,)  # match ':name' anywhere
    )
    candidates = cur.fetchall()
    if not candidates:
        # also try matching end with .name (for methods)
        cur.execute(
            """
            SELECT symbols.id AS id,
                   symbols.qualname AS qualname,
                   metrics.complexity AS complexity,
                   metrics.churn AS churn
            FROM symbols
            JOIN metrics ON metrics.symbol_id = symbols.id
            WHERE symbols.qualname LIKE '%' || ?
            ORDER BY metrics.complexity DESC, metrics.churn DESC
            """,
            ("." + name,),
        )
        candidates = cur.fetchall()
    if not candidates:
        return None
    # Choose candidate with highest complexity, then churn
    import math
    best = max(candidates, key=lambda r: r["complexity"] * (1.0 + math.sqrt(r["churn"])))
    return best["id"]


def get_callees(conn: sqlite3.Connection, symbol_id: int) -> List[Tuple[str, Optional[str], bool]]:
    """Return a list of callees for a given symbol.

    Each returned tuple is ``(qualname_or_name, file_path, unresolved)``.
    If the call was unresolved, ``file_path`` is ``None``.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT edges.callee_id AS callee_id,
               edges.callee_name AS callee_name,
               edges.unresolved AS unresolved,
               symbols.qualname AS qualname,
               files.path AS file_path
        FROM edges
        LEFT JOIN symbols ON edges.callee_id = symbols.id
        LEFT JOIN files ON symbols.file_id = files.id
        WHERE edges.caller_id = ?
        ORDER BY edges.id
        """,
        (symbol_id,),
    )
    results: List[Tuple[str, Optional[str], bool]] = []
    for row in cur.fetchall():
        if row["unresolved"]:
            results.append((row["callee_name"], None, True))
        else:
            results.append((row["qualname"], row["file_path"], False))
    return results


def get_callers(conn: sqlite3.Connection, symbol_id: int) -> List[Tuple[str, str]]:
    """Return a list of callers for a given symbol.

    Each tuple contains the caller qualname and the relative file path.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbols.qualname AS qualname,
               files.path AS file_path
        FROM edges
        JOIN symbols ON edges.caller_id = symbols.id
        JOIN files ON symbols.file_id = files.id
        WHERE edges.callee_id = ?
        ORDER BY edges.id
        """,
        (symbol_id,),
    )
    return [(row["qualname"], row["file_path"]) for row in cur.fetchall()]


def close(conn: sqlite3.Connection) -> None:
    """Close the SQLite connection."""
    conn.close()
