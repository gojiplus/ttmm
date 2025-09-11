"""Command line interface for ttmm.

This module exposes a ``main`` function that can be installed as a
console script entry point.  It supports subcommands for indexing,
listing hotspots, resolving callers/callees, running traces and
answering questions.
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from . import index, store, trace, search, gitingest


def do_index(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path)
    if repo_path is None:
        print(f"Failed to fetch repository: {args.path}")
        sys.exit(1)

    try:
        index.index_repo(repo_path)
        print(f"Indexed repository {args.path}")
    finally:
        # Clean up temp directory if it was a remote fetch
        if repo_path != args.path and repo_path.startswith('/tmp'):
            gitingest.cleanup_temp_repo(repo_path)


def do_hotspots(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path, temp_ok=False)
    if repo_path is None:
        print(f"Repository not found or not indexed: {args.path}")
        sys.exit(1)

    conn = store.connect(repo_path)
    try:
        rows = store.get_hotspots(conn, limit=args.limit)
        if not rows:
            print("No hotspot data found. Did you index the repository?")
            return
        for row in rows:
            score = row["complexity"] * (1.0 + (row["churn"] or 0) ** 0.5)
            complexity_info = f"complexity={row['complexity']:.1f}"
            churn_info = f"churn={row['churn']:.3f}, score={score:.2f}"
            print(
                f"{row['qualname']} ({row['file_path']}:{row['lineno']}) – {complexity_info}, "
                f"{churn_info}"
            )
    finally:
        store.close(conn)


def do_callers(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path, temp_ok=False)
    if repo_path is None:
        print(f"Repository not found or not indexed: {args.path}")
        sys.exit(1)

    conn = store.connect(repo_path)
    try:
        sid = store.resolve_symbol(conn, args.symbol)
        if sid is None:
            print(f"Symbol '{args.symbol}' not found")
            return
        callers = store.get_callers(conn, sid)
        if not callers:
            print("No callers found.")
        else:
            for qualname, path in callers:
                print(f"{qualname} ({path})")
    finally:
        store.close(conn)


def do_callees(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path, temp_ok=False)
    if repo_path is None:
        print(f"Repository not found or not indexed: {args.path}")
        sys.exit(1)

    conn = store.connect(repo_path)
    try:
        sid = store.resolve_symbol(conn, args.symbol)
        if sid is None:
            print(f"Symbol '{args.symbol}' not found")
            return
        callees = store.get_callees(conn, sid)
        if not callees:
            print("No callees found.")
        else:
            for name, path, unresolved in callees:
                suffix = " (unresolved)" if unresolved else ""
                loc = f" ({path})" if path else ""
                print(f"{name}{loc}{suffix}")
    finally:
        store.close(conn)


def do_trace(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path, temp_ok=False)
    if repo_path is None:
        print(f"Repository not found or not indexed: {args.path}")
        sys.exit(1)

    # Flatten args after '--'
    target_args: List[str] = args.args if hasattr(args, "args") else []
    trace.run_tracing(repo_path, module=args.module, script=args.script, args=target_args)
    print("Trace completed")


def do_answer(args: argparse.Namespace) -> None:
    repo_path = _resolve_repo_path(args.path, temp_ok=False)
    if repo_path is None:
        print(f"Repository not found or not indexed: {args.path}")
        sys.exit(1)

    results = search.answer_question(repo_path, args.question, top=args.limit, include_scores=True)
    if not results:
        print("No relevant symbols found.")
    else:
        for qualname, path, lineno, score in results:
            print(f"{qualname} ({path}:{lineno}) – score={score:.2f}")


def _resolve_repo_path(path_or_url: str, temp_ok: bool = True) -> str | None:
    """Resolve a path or URL to a local repository path.

    For URLs, fetches the repository. For local paths, validates existence.

    Parameters
    ----------
    path_or_url : str
        Local path, Git URL, or GitIngest URL
    temp_ok : bool
        Whether to allow temporary directory creation for remote repos

    Returns
    -------
    str or None
        Local path to repository, or None if resolution failed
    """
    import os

    # If it's a local path that exists, return it
    if os.path.exists(path_or_url):
        return os.path.abspath(path_or_url)

    # If temp directories are not allowed, only work with local paths
    if not temp_ok:
        return None

    # Try to fetch as a remote repository
    return gitingest.fetch_repository(path_or_url)


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ttmm", description="Time‑to‑Mental‑Model code reading assistant"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    # index
    p_index = sub.add_parser("index", help="Index a Python repository")
    p_index.add_argument(
        "path", help="Path, Git URL, or GitIngest URL of repository"
    )
    p_index.set_defaults(func=do_index)
    # hotspots
    p_hot = sub.add_parser("hotspots", help="Show hottest functions/methods")
    p_hot.add_argument("path", help="Path to repository")
    p_hot.add_argument("--limit", type=int, default=10, help="Number of results to show")
    p_hot.set_defaults(func=do_hotspots)
    # callers
    p_callers = sub.add_parser("callers", help="Show functions that call the given symbol")
    p_callers.add_argument("path", help="Path to repository")
    p_callers.add_argument("symbol", help="Fully qualified or simple symbol name")
    p_callers.set_defaults(func=do_callers)
    # callees
    p_callees = sub.add_parser("callees", help="Show functions called by the given symbol")
    p_callees.add_argument("path", help="Path to repository")
    p_callees.add_argument("symbol", help="Fully qualified or simple symbol name")
    p_callees.set_defaults(func=do_callees)
    # trace
    p_trace = sub.add_parser(
        "trace", help="Trace runtime execution of a module function or script"
    )
    p_trace.add_argument("path", help="Path to repository")
    group = p_trace.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--module", help="Module entry point in form pkg.module:func or pkg.module to run"
    )
    group.add_argument("--script", help="Relative path to a Python script to run")
    p_trace.add_argument(
        "args", nargs=argparse.REMAINDER,
        help="Arguments passed to the module function or script"
    )
    p_trace.set_defaults(func=do_trace)
    # answer
    p_answer = sub.add_parser("answer", help="Answer a question about the codebase")
    p_answer.add_argument("path", help="Path to repository")
    p_answer.add_argument("question", help="Natural language question or keywords")
    p_answer.add_argument("--limit", type=int, default=5, help="Number of answers to return")
    p_answer.set_defaults(func=do_answer)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
