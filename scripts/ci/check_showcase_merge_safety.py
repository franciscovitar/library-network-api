"""Protect the published showcase from unauthorized pull request changes.

The only permitted showcase edit is a strictly safer Vercel deployment lock:
existing vetoes stay in place, enabled branches may be vetoed, and new branch
entries must be disabled. All other showcase files and Vercel settings are
immutable through this guard.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

CONFIG_PATH = "showcase/vercel.json"


class DuplicateJsonKey(ValueError):
    """Reject ambiguous JSON objects instead of relying on last-key-wins parsing."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_config(source: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(source, object_pairs_hook=_object_without_duplicate_keys)
    except (json.JSONDecodeError, DuplicateJsonKey) as exc:
        raise ValueError(f"{label} is not unambiguous valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _deployment_rules(config: dict[str, Any], label: str) -> dict[str, bool]:
    git_config = config.get("git", {})
    if not isinstance(git_config, dict):
        raise ValueError(f"{label} git setting must be an object")
    rules = git_config.get("deploymentEnabled", {})
    if not isinstance(rules, dict):
        raise ValueError(f"{label} git.deploymentEnabled must be an object")
    if any(
        not isinstance(name, str) or not _is_literal_branch_name(name) or type(enabled) is not bool
        for name, enabled in rules.items()
    ):
        raise ValueError(f"{label} deployment rules must map branch names to booleans")
    return rules


def _is_literal_branch_name(name: str) -> bool:
    """Reject wildcard-like Vercel rules so only exact branch vetoes are allowed."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._/-]*", name):
        return False
    if ".." in name or "//" in name or "@{" in name or name.endswith(("/", ".", ".lock")):
        return False
    return all(not part.startswith(".") and not part.endswith(".lock") for part in name.split("/"))


def _without_deployment_rules(config: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(config))
    git_config = result.get("git")
    if isinstance(git_config, dict):
        git_config.pop("deploymentEnabled", None)
        if not git_config:
            result.pop("git")
    return result


def validate_showcase_changes(
    changed_paths: Sequence[str],
    base_config: str | None,
    head_config: str | None,
    *,
    base_mode: str = "100644 blob",
    head_mode: str = "100644 blob",
) -> str | None:
    """Return a rejection reason, or None when the showcase diff is safe."""
    paths = sorted(set(changed_paths))
    if not paths:
        return None
    if paths != [CONFIG_PATH]:
        return f"unauthorized showcase paths changed: {paths}"
    if base_mode != "100644 blob" or head_mode != "100644 blob":
        return "showcase/vercel.json must remain a regular non-executable file"
    if base_config is None or head_config is None:
        return "cannot validate a missing base or proposed Vercel configuration"

    try:
        original = _parse_config(base_config, "base vercel.json")
        proposed = _parse_config(head_config, "proposed vercel.json")
        original_rules = _deployment_rules(original, "base")
        proposed_rules = _deployment_rules(proposed, "proposed")
    except ValueError as exc:
        return str(exc)

    if _without_deployment_rules(original) != _without_deployment_rules(proposed):
        return "only git.deploymentEnabled may change in showcase/vercel.json"

    for branch, enabled in original_rules.items():
        proposed_value = proposed_rules.get(branch)
        if proposed_value is None:
            return f"existing deployment rule for {branch!r} was removed"
        if enabled is False and proposed_value is not False:
            return f"existing deployment veto for {branch!r} cannot be lifted"
        if enabled is True and proposed_value not in (True, False):
            return f"deployment rule for {branch!r} must remain boolean"

    added_branches = proposed_rules.keys() - original_rules.keys()
    enabled_branches = sorted(
        branch for branch in added_branches if proposed_rules[branch] is not False
    )
    if enabled_branches:
        return f"new deployment rules must be vetoes (false): {enabled_branches}"
    if proposed_rules.get("main") is not False:
        return "main must remain explicitly disabled when deployment rules change"
    return None


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.STDOUT)


def _config_at(revision: str) -> str | None:
    try:
        return _git("show", f"{revision}:{CONFIG_PATH}").decode("utf-8")
    except subprocess.CalledProcessError:
        return None


def _mode_at(revision: str) -> str | None:
    try:
        entries = [
            entry
            for entry in _git("ls-tree", "-z", revision, "--", CONFIG_PATH).split(b"\0")
            if entry
        ]
    except subprocess.CalledProcessError:
        return None
    if len(entries) != 1:
        return None
    metadata, path = entries[0].split(b"\t", 1)
    if path.decode("utf-8", errors="replace") != CONFIG_PATH:
        return None
    mode, object_type, _ = metadata.decode("ascii").split(" ", 2)
    return f"{mode} {object_type}"


def main() -> int:
    base = os.environ.get("BASE_SHA", "")
    head = os.environ.get("HEAD_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(r"[0-9a-f]{40}", head):
        print("BASE_SHA and HEAD_SHA must be full Git commit IDs", file=sys.stderr)
        return 2

    try:
        raw_paths = _git("diff", "--no-renames", "--name-only", "-z", base, head, "--", "showcase/")
        changed_paths = [
            item.decode("utf-8", errors="replace") for item in raw_paths.split(b"\0") if item
        ]
    except subprocess.CalledProcessError as exc:
        print(
            f"Could not inspect the showcase diff: {exc.output.decode(errors='replace')}",
            file=sys.stderr,
        )
        return 2

    reason = validate_showcase_changes(
        changed_paths,
        _config_at(base) if changed_paths else None,
        _config_at(head) if changed_paths else None,
        base_mode=_mode_at(base) if changed_paths else "100644 blob",
        head_mode=_mode_at(head) if changed_paths else "100644 blob",
    )
    if reason:
        print(f"SHOWCASE SAFETY CHECK FAILED: {reason}", file=sys.stderr)
        return 1
    if changed_paths:
        print("PASS: only explicit Vercel deployment vetoes changed; published content is intact.")
    else:
        print("PASS: showcase/ is unchanged.")
    print(
        "This CI guard does not prevent pre-CI deployments; "
        "verify Vercel before publishing branches."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
