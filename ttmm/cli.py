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

from . import index, store, trace, search


def do_index(args: argparse.Namespace) -> None:
    index.index_repo(args.path)
    print(f"Indexed repository {args.path}")


def do_hotspots(args: argparse.Namespace) -> None:
    conn = store.connect(args.path)
    try:
        rows = store.get_hotspots(conn, limit=args.limit)
        if not rows:
            print("No hotspot data found. Did you index the repository?")
            return
        for row in rows:
            score = row["complexity"] * (1.0 + (row["churn"] or 0) ** 0.5)
            print(
                f"{row['qualname']} ({row['file_path']}:{row['lineno']}) – complexity={row['complexity']:.1f}, "
                f"churn={row['churn']:.3f}, score={score:.2f}"
            )
    finally:
        store.close(conn)


def do_callers(args: argparse.Namespace) -> None:
    conn = store.connect(args.path)
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
    conn = store.connect(args.path)
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
    # Flatten args after '--'
    target_args: List[str] = args.args if hasattr(args, "args") else []
    trace.run_tracing(args.path, module=args.module, script=args.script, args=target_args)
    print("Trace completed")


def do_answer(args: argparse.Namespace) -> None:
    results = search.answer_question(args.path, args.question, top=args.limit, include_scores=True)
    if not results:
        print("No relevant symbols found.")
    else:
        for qualname, path, lineno, score in results:
            print(f"{qualname} ({path}:{lineno}) – score={score:.2f}")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ttmm", description="Time‑to‑Mental‑Model code reading assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    # index
    p_index = sub.add_parser("index", help="Index a Python repository")
    p_index.add_argument("path", help="Path to repository")
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
    p_trace = sub.add_parser("trace", help="Trace runtime execution of a module function or script")
    p_trace.add_argument("path", help="Path to repository")
    group = p_trace.add_mutually_exclusive_group(required=True)
    group.add_argument("--module", help="Module entry point in form pkg.module:func or pkg.module to run")
    group.add_argument("--script", help="Relative path to a Python script to run")
    p_trace.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the module function or script")
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
