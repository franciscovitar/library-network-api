"""Operational catalogue search reflects real database state and branch availability."""

import pytest

from tests.integration.helpers import API

pytestmark = pytest.mark.integration


def search(api, **params):
    return api.get(f"{API}/catalog/search", params=params)


def test_search_by_title_author_isbn_and_pagination(api):
    one = search(api, q="garden")
    assert one.status_code == 200, one.text
    assert [book["title"] for book in one.json()["items"]] == ["The Garden of Test Data"]
    assert one.json()["total"] == 1
    by_author = search(api, q="sample")
    assert by_author.json()["items"][0]["author"] == "B. Sample"
    by_isbn = search(api, q="0000-0004")
    assert by_isbn.json()["items"][0]["title"] == "Maps of Nowhere"
    paged = search(api, limit=2, offset=0)
    assert paged.status_code == 200
    assert paged.json()["total"] == 5
    assert len(paged.json()["items"]) == 2
    assert paged.json()["items"][0]["title"] <= paged.json()["items"][1]["title"]


def test_search_counts_available_copies_by_branch(api):
    all_branches = search(api, q="synthetic tales").json()["items"][0]
    assert (all_branches["total_copies"], all_branches["available_copies"]) == (2, 2)
    branch_one = search(api, q="synthetic tales", branch_id=1).json()["items"][0]
    assert (branch_one["total_copies"], branch_one["available_copies"]) == (1, 1)
    branch_three = search(api, q="synthetic tales", branch_id=3).json()["items"][0]
    assert (branch_three["total_copies"], branch_three["available_copies"]) == (0, 0)


def test_catalog_excludes_unavailable_when_requested(api):
    before = search(api, q="mock libraries", branch_id=1).json()
    assert (before["items"][0]["total_copies"], before["items"][0]["available_copies"]) == (
        1,
        0,
    )
    filtered = search(api, q="mock libraries", branch_id=1, available_only=True).json()
    assert filtered["total"] == 0
    assert filtered["items"] == []


def test_catalog_changes_after_transactional_checkout_and_return(api):
    before = search(api, q="synthetic tales", branch_id=1).json()["items"][0]
    assert before["available_copies"] == 1
    loan = api.post(
        f"{API}/loans/local",
        json={"member_id": 1, "copy_id": 1, "branch_id": 1},
        headers={"Idempotency-Key": "catalog-live-1"},
    )
    assert loan.status_code == 201, loan.text
    after = search(api, q="synthetic tales", branch_id=1).json()["items"][0]
    assert after["available_copies"] == 0
    returned = api.post(
        f"{API}/loans/{loan.json()['id']}/local-return",
        json={"branch_id": 1, "condition": "GOOD"},
    )
    assert returned.status_code == 200, returned.text
    restored = search(api, q="synthetic tales", branch_id=1).json()["items"][0]
    assert restored["available_copies"] == 1


def test_search_validation_and_unknown_branch(api):
    unknown = search(api, branch_id=999)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "branch_not_found"
    assert search(api, q="a" * 121).status_code == 422
    assert search(api, limit=101).status_code == 422
    # A literal SQL wildcard is escaped, not treated as 'match everything'.
    assert search(api, q="%").json()["items"] == []
