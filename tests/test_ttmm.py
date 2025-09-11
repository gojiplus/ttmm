"""Basic tests for the ttmm package.

These tests create a small temporary repository on the fly, index it,
and verify that symbol extraction, call resolution, hotspot scoring and
search behave as expected.  They are intentionally simple and do not
cover every corner case; the goal is to provide smoke coverage for
continuous integration.
"""

from __future__ import annotations

import os
import tempfile
import textwrap

import pytest

from zerottmm import index as ttmm_index
from zerottmm import store as ttmm_store
from zerottmm import search as ttmm_search


def create_sample_repo(tmp_path) -> str:
    """Create a small sample Python project for testing.

    The project has two files:

    * ``alpha.py`` defines ``foo`` which calls ``bar``; ``bar`` does nothing.
    * ``beta.py`` defines a class ``Widget`` with method ``ping`` which
      calls ``foo``.
    """
    alpha = textwrap.dedent(
        """
        def foo():
            '''Foo does something and calls bar.'''
            bar()

        def bar():
            return None
        """
    )
    beta = textwrap.dedent(
        """
        class Widget:
            def ping(self):
                # ping calls foo from alpha
                from alpha import foo
                foo()
        """
    )
    repo = tmp_path
    (repo / "alpha.py").write_text(alpha)
    (repo / "beta.py").write_text(beta)
    return str(repo)


def test_index_and_hotspots_and_call_graph(tmp_path):
    repo = create_sample_repo(tmp_path)
    ttmm_index.index_repo(repo)
    conn = ttmm_store.connect(repo)
    try:
        # Check that foo and bar and Widget.ping are present
        sid_foo = ttmm_store.resolve_symbol(conn, "alpha:foo")
        sid_bar = ttmm_store.resolve_symbol(conn, "alpha:bar")
        sid_ping = ttmm_store.resolve_symbol(conn, "beta:Widget.ping")
        assert sid_foo and sid_bar and sid_ping
        # Check callees: foo should call bar
        callees = ttmm_store.get_callees(conn, sid_foo)
        assert any(name == "alpha:bar" and not unresolved for name, path, unresolved in callees)
        # Check callers: bar should have foo as caller
        callers_bar = ttmm_store.get_callers(conn, sid_bar)
        assert any(name == "alpha:foo" for name, _ in callers_bar)
        # Hotspots should include these three symbols
        hotspots = ttmm_store.get_hotspots(conn, limit=10)
        qualnames = [row["qualname"] for row in hotspots]
        assert "alpha:foo" in qualnames
        assert "alpha:bar" in qualnames
        assert "beta:Widget.ping" in qualnames
    finally:
        ttmm_store.close(conn)


def test_search_answers(tmp_path):
    repo = create_sample_repo(tmp_path)
    ttmm_index.index_repo(repo)
    # Ask about bar
    results = ttmm_search.answer_question(repo, "call bar", top=3, include_scores=False)
    # Expect foo to appear because foo calls bar
    qualnames = [r[0] for r in results]
    assert any(qn.endswith(":foo") for qn in qualnames)
    assert any(qn.endswith(":bar") for qn in qualnames)
