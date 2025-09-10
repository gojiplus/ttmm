"""Utilities for computing git churn.

The hotspot score used by ttmm combines cyclomatic complexity and recent
development activity.  ``compute_churn`` uses ``git log --numstat`` to
approximate how much each file has changed recently.  A half‑life decay
is applied so that more recent commits contribute more to the churn.

If ``git`` is not installed or the repository is not a git repository,
``compute_churn`` will return an empty dictionary, in which case
complexity alone determines the hotspot score.
"""

from __future__ import annotations

import subprocess
import time
import os
from typing import Dict, Optional


def _run_git(args, cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout
    except Exception:
        return None


def compute_churn(
    repo_path: str,
    half_life_days: float = 90.0,
    since_days: float = 365.0,
) -> Dict[str, float]:
    """Compute a recency‑weighted churn score for each file in a git repository.

    Parameters
    ----------
    repo_path: str
        Path to the repository root.  Must contain a ``.git`` directory.
    half_life_days: float
        The half‑life for decay in days.  Commits older than this
        contribute half as much churn as very recent commits.
    since_days: float
        Limit churn calculation to this many days in the past.  Setting
        a finite window improves performance on large repositories.

    Returns
    -------
    Dict[str, float]
        Mapping from relative file path to a churn value.  Paths use
        forward slashes regardless of platform.  If ``git`` is not
        available or no repository exists, returns an empty dict.
    """
    # Verify .git exists
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return {}
    # Build git log command
    now = time.time()
    since_timestamp = now - since_days * 86400
    since_date = time.strftime("%Y-%m-%d", time.gmtime(since_timestamp))
    output = _run_git([
        "-c", "log.showSignature=false",  # suppress GPG signature noise
        "log",
        "--numstat",
        f"--since={since_date}",
        "--pretty=format:%ct",
    ], cwd=repo_path)
    if output is None:
        return {}
    churn: Dict[str, float] = {}
    lines = output.splitlines()
    commit_time: Optional[int] = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            # Start of a commit: epoch time
            try:
                commit_time = int(line)
            except Exception:
                commit_time = None
        else:
            if commit_time is None:
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            adds_str, dels_str, path = parts
            # Convert additions/deletions; "-" means binary or untracked
            try:
                adds = int(adds_str) if adds_str != "-" else 0
            except Exception:
                adds = 0
            try:
                dels = int(dels_str) if dels_str != "-" else 0
            except Exception:
                dels = 0
            total = adds + dels
            # Weight by recency
            age_days = (now - commit_time) / 86400.0
            weight = 0.0
            if half_life_days > 0:
                # Exponential decay: half‑life h -> weight = 0.5^(age/h)
                weight = 0.5 ** (age_days / half_life_days)
            else:
                weight = 1.0
            churn.setdefault(path, 0.0)
            churn[path] += total * weight
    return churn
