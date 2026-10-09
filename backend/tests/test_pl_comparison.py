"""真实PL核对的归组、权限和导出边界；假客户端只允许GET。"""

import base64
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.business.pl_comparison_service import PlComparisonService
from backend.modules.business.pl_comparison_vo import ComparisonResult
from backend.tests.test_pl_lookup import LookupNS
from fastapi.testclient import TestClient


@pytest.fixture
def ns():
    client = LookupNS()
    client.settings.account = "test-sb1"
    client.settings.pl_lookup["company_record_type"] = "classification"
    client.index["customs_line", "pl", "1"] = ["200", "202"]
    for record in client.data.values():
        company = record.get("company")
        if company:
            company["refName"] = "测试公司甲" if company["id"] == "3" else "测试公司乙"
    return client


def test_group_by_company_identity_without_cartesian_product(ns):
    result = PlComparisonService(ns).query("PL001")
    ComparisonResult.model_validate(result)
    assert len(result["groups"]) == 2
    assert sum(len(g["purchases"]) + len(g["customs"]) for g in result["groups"]) == 4
    assert result["groups"][0]["id"] != result["groups"][1]["id"]
    first = next(g for g in result["groups"] if g["company"] == "测试公司甲")
    assert len(first["customs"]) == 1 and len(first["purchases"]) == 2
    assert first["purchases"][0]["cells"][14] == "22880.000001"
    assert all(r["cells"][13] == "待确认" for g in result["groups"] for r in g["customs"] + g["purchases"])
    assert ns.calls.count(("customs_line", "200")) == 1


@pytest.mark.parametrize("company", ["公司甲", "3"])
def test_filter_applies_to_both_sources_and_export(ns, company):
    result = PlComparisonService(ns).query("PL001", company)
    assert len(result["groups"]) == 1
    group = result["groups"][0]
    assert len(group["purchases"]) == 2 and len(group["customs"]) == 1
    with ZipFile(BytesIO(base64.b64decode(result["download"]["contentBase64"]))) as archive:
        for name in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
            xml = archive.read(name).decode()
            ET.fromstring(xml)
            assert "测试公司乙" not in xml and "另一公司" not in xml
            assert "待确认" in xml and "22880.000001" in xml
    assert PlComparisonService(ns).query("PL001", "无此公司")["download"] is None


def test_customs_read_independently_even_without_purchases(ns):
    ns.index["purchase", "pl", "1"] = []
    result = PlComparisonService(ns).query("PL001")
    assert len(result["groups"]) == 2
    assert all(g["status"] == "缺少采购明细" for g in result["groups"])


def test_same_names_do_not_merge_distinct_ids_and_missing_ids_stay_separate(ns):
    ns.data["customs_line", "202"]["company"]["refName"] = "测试公司甲"
    result = PlComparisonService(ns).query("PL001", "测试公司甲")
    assert len(result["groups"]) == 2
    for key in (("purchase", "10"), ("purchase", "11")):
        ns.data[key].pop("company")
    result = PlComparisonService(ns).query("PL001")
    assert len(result["groups"]) == 4
    assert len(result["warnings"]) == 2


@pytest.mark.parametrize("failure", ["duplicate", "missing_parent", "wrong_pl", "changed_listing"])
def test_incomplete_upstream_fails_without_export(ns, failure):
    if failure == "duplicate":
        ns.index["customs_line", "pl", "1"].append("200")
    elif failure == "missing_parent":
        ns.data["customs_line", "200"].pop("parent")
    elif failure == "wrong_pl":
        ns.data["customs_line", "200"]["pl"] = {"id": "9"}
    else:
        ns.index["customs_line", "parent", "20"].remove("200")
    with pytest.raises(ApiError):
        PlComparisonService(ns).query("PL001")


def test_excel_retains_precision_and_treats_formula_text_as_literal(ns):
    ns.data["purchase_line", "100"]["amount"] = Decimal("22880.000000000001")
    ns.data["customs_line", "200"]["name"] = '=HYPERLINK("https://example.invalid")'
    result = PlComparisonService(ns).query("PL001", "3")
    with ZipFile(BytesIO(base64.b64decode(result["download"]["contentBase64"]))) as archive:
        for name in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
            root = ET.fromstring(archive.read(name))
            assert not root.findall(".//{*}f")
            precise = [c for c in root.findall(".//{*}c") if "22880.000000000001" in "".join(c.itertext())]
            assert len(precise) == 1 and precise[0].attrib["t"] == "inlineStr"


def test_missing_company_reference_type_fails_before_reading(ns):
    ns.settings.pl_lookup.pop("company_record_type")
    with pytest.raises(ApiError, match="company_record_type"):
        PlComparisonService(ns).query("PL001")
    assert ns.calls == []


def test_endpoint_requires_identity_and_validates_inputs(context):
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app) as client:
        assert client.post("/api/ns/pl-comparison", json={"pl": "PL001"}).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        for body in (
            {"pl": "   "},
            {"pl": 'bad"'},
            {"pl": "PL001", "company": "x" * 121},
            {"pl": "PL001", "role": "admin"},
        ):
            response = client.post("/api/ns/pl-comparison", json=body, headers=headers)
            assert response.status_code in (400, 422)
        assert client.post("/api/ns/pl-comparison", json={"pl": "PL001"}, headers=headers).status_code == 503
