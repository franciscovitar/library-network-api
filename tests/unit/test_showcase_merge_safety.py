import json

import pytest

from scripts.ci.check_showcase_merge_safety import validate_showcase_changes

CONFIG = "showcase/vercel.json"
BASE = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "headers": [{"source": "/(.*)", "headers": [{"key": "X-Frame-Options", "value": "DENY"}]}],
    "git": {"deploymentEnabled": {"main": False, "old-branch": False, "active-branch": True}},
}


def encoded(config):
    return json.dumps(config)


def test_unchanged_showcase_is_approved_without_needing_config_readback():
    assert validate_showcase_changes([], None, None) is None


def test_additional_branch_veto_is_approved():
    proposed = json.loads(encoded(BASE))
    proposed["git"]["deploymentEnabled"]["new-branch"] = False
    assert validate_showcase_changes([CONFIG], encoded(BASE), encoded(proposed)) is None


def test_turning_an_enabled_branch_into_a_veto_is_approved():
    proposed = json.loads(encoded(BASE))
    proposed["git"]["deploymentEnabled"]["active-branch"] = False
    assert validate_showcase_changes([CONFIG], encoded(BASE), encoded(proposed)) is None


@pytest.mark.parametrize("path", ["showcase/index.html", "showcase/other.json"])
def test_published_showcase_files_are_rejected(path):
    reason = validate_showcase_changes([path], encoded(BASE), encoded(BASE))
    assert reason is not None
    assert "unauthorized showcase paths" in reason


def test_unrelated_vercel_settings_are_rejected():
    proposed = json.loads(encoded(BASE))
    proposed["headers"][0]["headers"][0]["value"] = "SAMEORIGIN"
    reason = validate_showcase_changes([CONFIG], encoded(BASE), encoded(proposed))
    assert reason == "only git.deploymentEnabled may change in showcase/vercel.json"


def test_new_branch_cannot_be_enabled():
    proposed = json.loads(encoded(BASE))
    proposed["git"]["deploymentEnabled"]["new-branch"] = True
    reason = validate_showcase_changes([CONFIG], encoded(BASE), encoded(proposed))
    assert reason is not None
    assert "new deployment rules must be vetoes" in reason


def test_wildcard_deployment_rules_are_rejected():
    proposed = json.loads(encoded(BASE))
    proposed["git"]["deploymentEnabled"]["*"] = False
    reason = validate_showcase_changes([CONFIG], encoded(BASE), encoded(proposed))
    assert reason is not None
    assert "must map branch names to booleans" in reason


def test_existing_veto_cannot_be_removed_or_lifted():
    removed = json.loads(encoded(BASE))
    del removed["git"]["deploymentEnabled"]["old-branch"]
    assert "was removed" in validate_showcase_changes([CONFIG], encoded(BASE), encoded(removed))

    enabled = json.loads(encoded(BASE))
    enabled["git"]["deploymentEnabled"]["old-branch"] = True
    assert "cannot be lifted" in validate_showcase_changes(
        [CONFIG], encoded(BASE), encoded(enabled)
    )


def test_main_must_be_explicitly_vetoed():
    base = {"headers": BASE["headers"]}
    proposed = {**base, "git": {"deploymentEnabled": {"new-branch": False}}}
    reason = validate_showcase_changes([CONFIG], encoded(base), encoded(proposed))
    assert reason == "main must remain explicitly disabled when deployment rules change"


def test_ambiguous_json_is_rejected():
    ambiguous = '{"git":{"deploymentEnabled":{"main":false,"main":true}}}'
    reason = validate_showcase_changes([CONFIG], ambiguous, ambiguous)
    assert reason is not None
    assert "duplicate JSON key" in reason


def test_vercel_config_must_remain_a_regular_non_executable_file():
    reason = validate_showcase_changes(
        [CONFIG], encoded(BASE), encoded(BASE), head_mode="120000 blob"
    )
    assert reason == "showcase/vercel.json must remain a regular non-executable file"
