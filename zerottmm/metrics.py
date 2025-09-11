"""Metrics computation for ttmm.

This module provides functions to compute cyclomatic complexity and lines
of code for Python functions and methods.  Complexity is a simple
approximation based on counting branching constructs; it is not as
sophisticated as tools like radon or mccabe but suffices for guiding
reading order.  It does not require any third party dependencies.
"""

from __future__ import annotations

import ast


class ComplexityVisitor(ast.NodeVisitor):
    """AST visitor that accumulates cyclomatic complexity.

    The initial complexity is 1.  Each branching or boolean operator
    increments the count.  Attribute calls do not contribute to
    complexity here.
    """

    def __init__(self) -> None:
        self.complexity = 1

    def generic_visit(self, node: ast.AST) -> None:
        # Branching constructs increase complexity by 1
        if isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.While,
                ast.AsyncFor,
                ast.With,
                ast.AsyncWith,
                ast.Try,
                ast.ExceptHandler,
            ),
        ):
            self.complexity += 1
        elif isinstance(node, ast.BoolOp):
            # bool operations like ``a and b and c`` count len(values) - 1
            self.complexity += max(len(node.values) - 1, 0)
        # Continue traversing
        super().generic_visit(node)


def compute_complexity(node: ast.AST) -> int:
    """Compute a simple cyclomatic complexity for a function/method AST node."""
    visitor = ComplexityVisitor()
    visitor.visit(node)
    return visitor.complexity


def compute_loc(node: ast.AST) -> int:
    """Compute the number of lines of code covered by a node.

    Uses ``lineno`` and ``end_lineno`` attributes available on Python 3.8+
    AST nodes.  Returns at least 1 even if these attributes are missing.
    """
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is not None and end is not None and end >= start:
        return end - start + 1
    return 1
