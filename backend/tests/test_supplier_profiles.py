"""供应商档案及名称候选：真实隔离数据库，企微只读假适配器。"""

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.source.public import SourceDirectory
from backend.modules.task.dto.supplier_group_dto import GroupSave, SupplierGroupMatch, SupplierProfileQuery
from backend.modules.task.policy.supplier_group_policy import match_group
from backend.modules.task.service.supplier_group_service import SupplierGroupService
from backend.modules.task.service.supplier_profile_service import SupplierProfileService
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from fastapi.testclient import TestClient

USER = "user:admin"
NAME = "广州市江川印花设备有限公司"


def group(chat_id, name, owner="owner1"):
    return {
        "chatId": chat_id,
        "groupName": name,
        "userid": owner,
        "employee": "采购王女士",
        "memberCount": 8,
        "createdAt": 1700000000,
    }


class Wecom:
    def __init__(self):
        self.items = [
            group("short", "广州市江川印花设备采购群"),
            group("full", NAME + "外部群"),
            group("exact2", NAME, "owner2"),
            group("exact1", NAME),
            group("other", "其他客户群"),
        ]
        self.refreshes = []
        self.fail = False

    def groups(self, *, refresh=False):
        self.refreshes.append(refresh)
        if self.fail:
            raise ApiError(502, "企微网络不可用")
        return {"items": self.items, "unavailableCount": 2}

    def group(self, chat_id):
        if self.fail:
            raise ApiError(502, "企微网络不可用")
        return next(item for item in self.items if item["chatId"] == chat_id)


@pytest.fixture
def setup(engine, ns):
    first, second = purchase(), purchase("201")
    first[1]["custrecord_swc_subpo_vendor"] = {"id": "77", "refName": NAME}
    second[1]["custrecord_swc_subpo_vendor"] = {"id": "78", "refName": "浙江清泉包装有限公司"}
    save(ns, engine, bundle([first, second], [customs("870")]))
    directory, wecom = SourceDirectory(engine), Wecom()
    groups = SupplierGroupService(engine, directory, wecom)
    profiles = SupplierProfileService(engine, directory)
    supplier = profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0]
    return groups, profiles, supplier, wecom


def test_ranking_duplicate_names_pagination_and_no_automatic_binding(setup):
    groups, profiles, supplier, wecom = setup
    query = SupplierGroupMatch(supplierId=supplier.supplierId, pageSize=2, refresh=True)
    result = groups.match_wecom(query, USER)
    assert [item.chatId for item in result.items] == ["exact1", "exact2"]
    assert result.total == 4 and result.pages == 2 and result.unavailableCount == 2
    assert all("一致" in item.matchReason for item in result.items)
    page2 = groups.match_wecom(query.model_copy(update={"page": 2, "refresh": False}), USER)
    assert [item.chatId for item in page2.items] == ["full", "short"]
    assert wecom.refreshes == [True, False]
    assert profiles.browse(SupplierProfileQuery(status="unbound"), USER).total == 2


def test_normalization_short_names_and_manual_keyword():
    item = group("id", " ＡＢＣ　供应商有限公司 ")
    assert match_group("abc供应商有限公司", item)[0] == 0
    assert match_group("有限公司", group("id", "其他公司采购群")) is None
    assert match_group("江川有限公司", group("id", "江川采购群")) is None
    assert match_group(NAME, group("id", "江川采购群"), "江川")[0] == 3
    assert match_group(NAME, item, "不存在") is None


def test_bind_filter_account_owner_and_disable(setup):
    groups, profiles, supplier, wecom = setup
    assert profiles.browse(SupplierProfileQuery(), USER).total == 2
    result = groups.match_wecom(SupplierGroupMatch(supplierId=supplier.supplierId, keyword="owner2"), USER)
    assert [item.chatId for item in result.items] == ["exact2"]
    wecom.items[2]["employee"] = "实时群主"
    saved = groups.save(GroupSave(supplierId=supplier.supplierId, chatId="exact2", revision=0), USER)
    assert saved.employee == "实时群主"
    enabled = profiles.browse(SupplierProfileQuery(status="enabled", keyword="实时群主", pageSize=1), USER)
    assert enabled.total == 1 and enabled.items[0].binding.chatId == "exact2"
    assert profiles.browse(SupplierProfileQuery(status="unbound"), USER).total == 1
    # 概况计数不随关键字和状态筛选变化
    counts = profiles.browse(SupplierProfileQuery(status="unbound", keyword="不存在"), USER).counts
    assert counts == {"all": 2, "bound": 1, "unbound": 1, "notifyOff": 0}
    assert profiles.browse(SupplierProfileQuery(account="another-account"), USER).total == 0
    assert profiles.browse(SupplierProfileQuery(keyword="%"), USER).total == 0
    assert profiles.browse(SupplierProfileQuery(keyword="77"), USER).items[0].nsInternalId == "77"
    with pytest.raises(ApiError, match="已被修改"):
        groups.save(GroupSave(supplierId=supplier.supplierId, chatId="full", revision=0), USER)
    wecom.fail = True
    groups.save(GroupSave(supplierId=supplier.supplierId, chatId="exact2", revision=1, enabled=False), USER)
    assert profiles.browse(SupplierProfileQuery(status="disabled"), USER).total == 1
    with pytest.raises(ApiError, match="企微网络"):
        groups.match_wecom(SupplierGroupMatch(supplierId=supplier.supplierId), USER)


def test_identity_and_missing_supplier(setup):
    groups, profiles, supplier, wecom = setup
    assert not profiles.browse(SupplierProfileQuery(), "service:test").manage.allowed
    with pytest.raises(ApiError, match="只读"):
        groups.match_wecom(SupplierGroupMatch(supplierId=supplier.supplierId), "service:test")
    with pytest.raises(ApiError, match="不存在"):
        groups.match_wecom(SupplierGroupMatch(supplierId="999999"), USER)
    assert not wecom.refreshes


def test_directory_cache_status_is_returned_without_changing_matching(setup, monkeypatch):
    groups, _, supplier, wecom = setup
    metadata = {
        "directoryUpdatedAt": "2026-10-20T01:00:00+00:00",
        "directoryStale": True,
        "directoryRefreshing": True,
        "directoryRefreshError": "上次网络读取失败",
    }
    monkeypatch.setattr(
        wecom, "groups", lambda **_: {"items": wecom.items, "unavailableCount": 2, **metadata}
    )
    result = groups.match_wecom(SupplierGroupMatch(supplierId=supplier.supplierId, keyword="owner2"), USER)
    assert [item.chatId for item in result.items] == ["exact2"]
    assert {key: getattr(result, key) for key in metadata} == metadata


def test_http_profiles_and_match(context, engine, setup):
    _, _, supplier, wecom = setup
    app = create_app(context.settings, context.ns, engine, wecom=wecom)
    root = "/api/tasks/supplier-groups"
    with TestClient(app) as client:
        assert client.post(root + "/profiles/query", json={}).status_code == 401
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={"username": "admin", "password": context.settings.admin_password},
            ).status_code
            == 200
        )
        assert (
            client.post(root + "/profiles/query", headers=headers, json={"status": "unbound"}).json()["total"]
            == 2
        )
        result = client.post(root + "/wecom/match", headers=headers, json={"supplierId": supplier.supplierId})
        assert result.status_code == 200 and result.json()["total"] == 4
        assert (
            client.post(
                root + "/wecom/match",
                headers=headers,
                json={"supplierId": supplier.supplierId, "supplierName": "伪造"},
            ).status_code
            == 400
        )
        assert (
            client.post(root + "/profiles/query", headers=headers, json={"status": "unknown"}).status_code
            == 400
        )
