"""GitIngest integration for ttmm.

This module handles fetching repositories from GitIngest URLs and other
remote sources. It parses various Git hosting URLs (GitHub, GitLab, etc.)
and provides functionality to download and extract repositories for analysis.
"""

from __future__ import annotations

import os
import re
import tempfile
import shutil
import subprocess
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs


def _is_git_url(url: str) -> bool:
    """Check if a string looks like a Git repository URL."""
    git_patterns = [
        r'https?://github\.com/[^/]+/[^/]+',
        r'https?://gitlab\.com/[^/]+/[^/]+',
        r'https?://bitbucket\.org/[^/]+/[^/]+',
        r'git@github\.com:[^/]+/[^/]+\.git',
        r'git@gitlab\.com:[^/]+/[^/]+\.git',
        r'https?://.*\.git$',
    ]
    return any(re.match(pattern, url) for pattern in git_patterns)


def _parse_gitingest_url(url: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Parse a GitIngest URL to extract repository info.

    Returns (repo_url, branch, subpath) or None if not a GitIngest URL.
    """
    if 'gitingest.com' not in url:
        return None

    parsed = urlparse(url)
    if not parsed.query:
        return None

    query_params = parse_qs(parsed.query)
    repo_url = query_params.get('url', [None])[0]
    branch = query_params.get('branch', [None])[0]
    subpath = query_params.get('subpath', [None])[0]

    if repo_url:
        return repo_url, branch, subpath
    return None


def _normalize_repo_url(url: str) -> str:
    """Normalize a repository URL for cloning."""
    # Convert SSH URLs to HTTPS for easier cloning
    if url.startswith('git@'):
        # git@github.com:owner/repo.git -> https://github.com/owner/repo.git
        ssh_pattern = r'git@([^:]+):([^/]+)/([^/]+)(?:\.git)?'
        match = re.match(ssh_pattern, url)
        if match:
            host, owner, repo = match.groups()
            return f'https://{host}/{owner}/{repo}.git'

    # Ensure .git suffix for HTTPS URLs
    if not url.endswith('.git') and _is_git_url(url):
        return url + '.git'

    return url


def _clone_repository(
    repo_url: str, target_dir: str, branch: Optional[str] = None, shallow: bool = True
) -> bool:
    """Clone a repository to the target directory.

    Returns True if successful, False otherwise.
    """
    try:
        cmd = ['git', 'clone']
        if shallow:
            cmd.extend(['--depth', '1'])
        if branch:
            cmd.extend(['--branch', branch])
        cmd.extend([repo_url, target_dir])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0
    except (
        subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError
    ):
        return False


def fetch_repository(url_or_path: str, target_dir: Optional[str] = None) -> Optional[str]:
    """Fetch a repository from a URL or return a local path.

    Handles GitIngest URLs, direct Git URLs, and local paths.

    Parameters
    ----------
    url_or_path : str
        GitIngest URL, Git repository URL, or local file path.
    target_dir : str, optional
        Directory to clone into. If None, uses a temporary directory.

    Returns
    -------
    str or None
        Path to the repository directory, or None if fetch failed.
    """
    # If it's a local path, return as-is
    if os.path.exists(url_or_path):
        return os.path.abspath(url_or_path)

    # Parse GitIngest URL
    gitingest_info = _parse_gitingest_url(url_or_path)
    if gitingest_info:
        repo_url, branch, subpath = gitingest_info
        if not repo_url:
            return None
    else:
        # Check if it's a direct Git URL
        if _is_git_url(url_or_path):
            repo_url = url_or_path
            branch = None
            subpath = None
        else:
            return None

    # Normalize the repository URL
    repo_url = _normalize_repo_url(repo_url)

    # Create target directory
    if target_dir is None:
        target_dir = tempfile.mkdtemp(prefix='ttmm_repo_')
    else:
        os.makedirs(target_dir, exist_ok=True)

    # Clone the repository
    clone_success = _clone_repository(repo_url, target_dir, branch)
    if not clone_success:
        if target_dir.startswith(tempfile.gettempdir()):
            shutil.rmtree(target_dir, ignore_errors=True)
        return None

    # Handle subpath if specified
    if subpath:
        subpath_full = os.path.join(target_dir, subpath)
        if os.path.exists(subpath_full):
            return subpath_full

    return target_dir


def cleanup_temp_repo(repo_path: str) -> None:
    """Clean up a temporary repository directory."""
    if repo_path and repo_path.startswith(tempfile.gettempdir()):
        shutil.rmtree(repo_path, ignore_errors=True)


def get_repo_info(repo_path: str) -> dict:
    """Extract basic information about a repository.

    Returns a dictionary with repository metadata.
    """
    info = {
        'path': repo_path,
        'is_git': False,
        'remote_url': None,
        'branch': None,
        'commit': None,
    }

    # Check if it's a git repository
    git_dir = os.path.join(repo_path, '.git')
    if os.path.exists(git_dir):
        info['is_git'] = True

        try:
            # Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info['remote_url'] = result.stdout.strip()

            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info['branch'] = result.stdout.strip()

            # Get current commit
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info['commit'] = result.stdout.strip()[:8]

        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    return info
