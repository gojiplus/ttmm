"""Simple TF‑IDF search over ttmm symbols.

This module provides a function to answer a natural language question
about a codebase.  It ranks functions and methods by combining
keyword similarity with their hotspot score.  The goal is to return
a small set of entry points that the developer should read first to
understand the behaviour described by the query.
"""

from __future__ import annotations

import re
import math
from typing import Dict, List, Tuple

from . import store


def _tokenize(text: str) -> List[str]:
    """Split a string into lowercase alphanumeric tokens."""
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", text)]


def answer_question(
    repo_path: str,
    question: str,
    top: int = 5,
    include_scores: bool = False,
) -> List[Tuple[str, str, int, float]]:
    """Answer a question by returning a minimal set of relevant symbols.

    Parameters
    ----------
    repo_path: str
        Path to the repository root.  The repository must have been
        indexed previously.
    question: str
        Natural language query or keywords.
    top: int
        Number of symbols to return.
    include_scores: bool
        If True, return the computed score alongside each result.

    Returns
    -------
    List[Tuple[qualname, file_path, line_no, score]]
        Sorted list of symbol descriptors.  Each tuple contains the
        fully qualified name, the relative file path, the starting line
        number and the ranking score.  The score is omitted if
        ``include_scores`` is False.
    """
    question_tokens = _tokenize(question)
    if not question_tokens:
        return []
    conn = store.connect(repo_path)
    try:
        cur = conn.cursor()
        # Load all symbols with metrics
        cur.execute(
            """
            SELECT symbols.id AS id,
                   symbols.qualname AS qualname,
                   files.path AS file_path,
                   symbols.lineno AS lineno,
                   metrics.complexity AS complexity,
                   metrics.churn AS churn,
                   symbols.doc AS doc
            FROM symbols
            JOIN metrics ON metrics.symbol_id = symbols.id
            JOIN files ON files.id = symbols.file_id
            """
        )
        symbols_list = cur.fetchall()
        # Build inverted index: token -> {symbol_index: tf}
        token_df: Dict[str, int] = {}
        token_tf: Dict[str, Dict[int, int]] = {}
        docs: List[Dict[str, int]] = []
        for idx, row in enumerate(symbols_list):
            text_parts = [row["qualname"], row["doc"] or ""]
            tokens = _tokenize(" ".join(text_parts))
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            docs.append(tf)
            for t in tf:
                token_df[t] = token_df.get(t, 0) + 1
                token_tf.setdefault(t, {})[idx] = tf[t]
        n_docs = len(symbols_list)
        # Precompute idf for query tokens only to speed up
        idf: Dict[str, float] = {}
        for t in question_tokens:
            df = token_df.get(t, 0)
            # Add 1 to denominator to avoid division by zero
            idf[t] = math.log((n_docs + 1) / (df + 1)) + 1.0
        # Compute similarity for each symbol
        scores: List[Tuple[int, float]] = []
        for idx, row in enumerate(symbols_list):
            # Compute TF‑IDF dot product for query and document
            score = 0.0
            for t in question_tokens:
                tf = token_tf.get(t, {}).get(idx, 0)
                score += tf * idf.get(t, 0.0)
            if score > 0.0:
                # Multiply by hotspot score (complexity * sqrt(churn + 1))
                complexity = row["complexity"]
                churn = row["churn"]
                hotspot = complexity * (1.0 + math.sqrt(churn))
                score *= (hotspot + 1e-6)
                scores.append((idx, score))
        # Sort descending
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, s in scores[:top]:
            row = symbols_list[idx]
            if include_scores:
                results.append((row["qualname"], row["file_path"], row["lineno"], s))
            else:
                results.append((row["qualname"], row["file_path"], row["lineno"],))
        return results
    finally:
        store.close(conn)
