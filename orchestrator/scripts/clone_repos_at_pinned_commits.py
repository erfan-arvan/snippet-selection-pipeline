#!/usr/bin/env python3
"""One-off ops script: clone (or fix up) each repo in pipeline.yaml's `repos:` list at its
pinned `commit`, using its `url` - not the pipeline's job (it deliberately never clones
anything itself), but the single source of truth should be pipeline.yaml, not a separately
maintained shell script, which is exactly how the druid url/commit mismatch happened.

Idempotent per repo: verifies HEAD already matches the pinned commit before doing anything,
and skips cloning if so. Otherwise removes whatever's there (if anything) and re-clones fresh
at the pinned commit via a shallow fetch-by-SHA (GitHub supports fetching an exact commit
object directly, not just branch/tag refs).

Usage:
    python3 clone_repos_at_pinned_commits.py <pipeline.yaml> <dest_dir>
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def current_head(repo_dir: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def clone_at_commit(url: str, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=dest, check=True)
    subprocess.run(["git", "fetch", "--depth", "1", "origin", commit], cwd=dest, check=True)
    subprocess.run(["git", "checkout", "-q", commit], cwd=dest, check=True)


def main(pipeline_yaml_path: str, dest_dir: str) -> None:
    with open(pipeline_yaml_path) as f:
        config = yaml.safe_load(f)
    dest_root = Path(dest_dir)

    for repo in config["repos"]:
        name, url, commit = repo["name"], repo.get("url"), repo.get("commit")
        repo_dir = dest_root / name

        if not url or not commit:
            print(f"SKIP {name}: no url/commit pinned in pipeline.yaml")
            continue

        existing_head = current_head(repo_dir) if repo_dir.is_dir() else None
        if existing_head == commit:
            print(f"OK   {name}: already at pinned commit {commit}")
            continue

        if repo_dir.exists():
            print(f"     {name}: at {existing_head or '(not a git repo)'}, pinned is {commit} - re-cloning")
            shutil.rmtree(repo_dir)
        else:
            print(f"     {name}: cloning fresh at pinned commit {commit}")

        try:
            clone_at_commit(url, commit, repo_dir)
            print(f"OK   {name}: now at {commit}")
        except subprocess.CalledProcessError as e:
            print(f"FAILED {name}: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <pipeline.yaml> <dest_dir>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
