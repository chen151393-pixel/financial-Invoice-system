"""超大 NS 集合自动拆分：乱序 ID、完整覆盖、范围隔离及后台请求幂等。"""

import random
import re

import pytest
from backend.core.errors import ApiError
from backend.modules.sync.dto.source_dto import PullCursor, PullRequest
from backend.modules.sync.service.pull_cursor_service import read_cursor_page
from backend.tests.test_sync_pull import sync_api as sync_api


class Collection:
    def __init__(self, size, *, totals=True):
        self.ids = list(range(1, size + 1))
        random.Random(42).shuffle(self.ids)
        self.calls = []
        self.totals = totals

    def request(self, method, record_type, *, query_params, exact_numbers):
        assert method == "GET" and exact_numbers
        self.calls.append(query_params)
        query = query_params.get("q", "")
        lower = re.search(r"id GREATER (\d+)", query)
        upper = re.search(r"id LESS_OR_EQUAL (\d+)", query)
        ids = [
            value
            for value in self.ids
            if (not lower or value > int(lower[1])) and (not upper or value <= int(upper[1]))
        ]
        offset, limit = query_params["offset"], query_params["limit"]
        assert offset < limit * 1000
        return {
            "data": {
                "items": [{"id": str(value)} for value in ids[offset : offset + limit]],
                "hasMore": offset + limit < len(ids),
                **({"totalResults": len(ids)} if self.totals else {}),
            }
        }


@pytest.mark.parametrize("size,limit,totals", [(20005, 20, True), (1005, 1, True), (20005, 20, False)])
def test_all_records_across_unordered_ranges_without_total_limit(size, limit, totals):
    ns = Collection(size, totals=totals)
    cursor = PullCursor(afterId="0")
    received = []
    batches = 0
    condition = 'created ON_OR_AFTER "2026-01-01" AND created BEFORE "2027-01-01"'
    while cursor is not None:
        request = PullRequest(offset=batches * limit, limit=limit, cursor=cursor)
        data, following = read_cursor_page(
            ns, "customrecord_customs", {"limit": limit, "q": condition}, request.cursor
        )
        received.extend(int(item["id"]) for item in data["items"])
        cursor = PullCursor(**following) if following else None
        batches += 1
        assert batches <= size + 1
    assert sorted(received) == list(range(1, size + 1))
    assert len(set(received)) == size
    assert all(call["q"].startswith(condition) for call in ns.calls)
    if size > 1000:
        assert batches > 1000


def test_sparse_large_ids_and_empty_remaining_range():
    ns = Collection(0)
    ns.ids = [10**20, 10**20 + 7, 10**20 + 999999]
    cursor = PullCursor(afterId=str(10**20 - 1), throughId=str(10**20 + 7))
    data, following = read_cursor_page(ns, "customrecord_customs", {"limit": 20}, cursor)
    assert len(data["items"]) == 2
    assert following == {"afterId": str(10**20 + 7), "throughId": None, "offset": 0}
    data, following = read_cursor_page(ns, "customrecord_customs", {"limit": 20}, PullCursor(**following))
    assert data["items"] == [{"id": str(10**20 + 999999)}]
    assert following is None
    data, following = read_cursor_page(
        ns, "customrecord_customs", {"limit": 20}, PullCursor(afterId=str(10**20 + 999999))
    )
    assert data["items"] == [] and following is None


@pytest.mark.parametrize(
    "data",
    [
        {"items": [{"id": "10"}], "hasMore": False},
        {"items": [{"id": "21"}], "hasMore": False},
        {"items": [{"id": "11"}, {"id": "11"}], "hasMore": False},
        {"items": [], "hasMore": True},
        {"items": [{"id": "11"}], "hasMore": False, "totalResults": "1"},
        {"items": [{"id": "11"}], "hasMore": True},
        {"items": [{"id": "11"}], "hasMore": False, "totalResults": 2},
        {"items": [{"id": "11"}], "hasMore": False, "offset": 20},
        {"items": [{"id": "11"}], "hasMore": False, "count": 2},
    ],
)
def test_invalid_upstream_range_is_not_reported_as_success(data):
    class NS:
        def request(self, *args, **kwargs):
            return {"data": data}

    with pytest.raises(ApiError):
        read_cursor_page(
            NS(), "customrecord_customs", {"limit": 20}, PullCursor(afterId="10", throughId="20")
        )


def test_api_accepts_more_than_1000_batches_and_continues_partition(sync_api):
    client, headers, context, calls = sync_api

    def request(method, record_type, record_id=None, **kwargs):
        calls.append(kwargs)
        if record_id:
            return {"data": {"id": record_id}}
        return {"data": {"items": [{"id": "11"}], "hasMore": False, "totalResults": 1}}

    context.ns.request = request
    response = client.post(
        "/api/ns/sync/customs-declarations/pull",
        headers=headers,
        json={
            "offset": 100000,
            "cursor": {"afterId": "10", "throughId": "20", "offset": 0},
            "startDate": "2026-01-01",
            "endDate": "2026-12-31",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["hasMore"] is True and result["nextOffset"] == 100020
    assert result["nextCursor"] == {"afterId": "20", "throughId": None, "offset": 0}
    assert calls[0]["query_params"]["offset"] == 0
    assert (
        'created BEFORE "2027-01-01" AND id GREATER 10 AND id LESS_OR_EQUAL 20'
        in calls[0]["query_params"]["q"]
    )
    assert context.ns.writes == []


@pytest.mark.parametrize(
    "cursor",
    [
        {"afterId": "1 OR 1=1"},
        {"afterId": "20", "throughId": "10"},
        {"afterId": "0", "offset": 20000},
        {"afterId": "0", "offset": 1},
        {"afterId": "0", "offset": True},
        {"afterId": "0", "field": "other"},
    ],
)
def test_cursor_validation_happens_before_external_read(sync_api, cursor):
    client, headers, _, calls = sync_api
    response = client.post("/api/ns/sync/customs-declarations/pull", headers=headers, json={"cursor": cursor})
    assert response.status_code == 400 and calls == []
