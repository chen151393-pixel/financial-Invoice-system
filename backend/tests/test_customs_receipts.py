"""海关回执：文件解析、明细比对规则、导入换版、列表筛选与重新匹配。"""

import base64
import io
from decimal import Decimal

import pytest
from backend.core.errors import ApiError
from backend.modules.review.dto.customs_receipt_dto import (
    CustomsImportRequest,
    CustomsReceiptQuery,
    CustomsRematchRequest,
)
from backend.modules.review.policy.customs_match_policy import compare, compare_lines
from backend.modules.review.service.customs_receipt_parser import parse
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from openpyxl import Workbook

HEADERS = [
    "出口报关单号",
    "项号",
    "出口日期",
    "数据检查状态",
    "征免类型",
    "申报业务",
    "商品代码",
    "海关商品名称",
    "规格型号",
    "出口合同号",
    "监管方式",
    "成交方式",
    "成交单位",
    "成交数量",
    "成交货币",
    "成交总价",
    "美元离岸价",
    "法定单位",
    "法定出口数量",
    "关单信息",
    "使用标志",
    "境外收货人",
]


def row(number, item, name, unit, quantity, consignee="", total=100):
    return [
        number,
        item,
        "2026-10-29",
        "检查通过",
        "征税",
        "--",
        "4810990000",
        name,
        "",
        "YEX260827",
        "0110",
        "FOB",
        unit,
        quantity,
        "USD",
        total,
        total,
        "千克",
        quantity,
        "存在",
        "未使用",
        consignee,
    ]


def xlsx(rows, headers=HEADERS):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for values in rows:
        sheet.append(values)
    buffer = io.BytesIO()
    book.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode()


def ns_line(line_id, name, quantity, unit):
    return {
        "id": line_id,
        "line_no": str(line_id),
        "item_code": "",
        "name": name,
        "specification": "",
        "quantity": Decimal(quantity) if quantity is not None else None,
        "unit": unit,
    }


def item(no, name, quantity, unit):
    return {"item_no": no, "name": name, "deal_quantity": Decimal(quantity), "deal_unit": unit}


# ---------- 比对规则 ----------


def test_one_ns_line_split_into_customs_items_matches_on_total():
    groups = compare_lines(
        [ns_line(1, "相纸", "4360.30", "千克")],
        [item("01", "相纸", "4315.80000", "千克"), item("02", "相纸", "44.50000", "千克")],
    )
    assert [g["status"] for g in groups] == ["split"]
    assert groups[0]["items"] == ["01", "02"] and "4360.3 千克" in groups[0]["note"]
    status, ns_id, _ = compare(
        [{"id": 9, "record_no": "CD1", "lines": [ns_line(1, "相纸", "4360.3", "千克")]}],
        [item("01", "相纸", "4315.8", "千克"), item("02", "相纸", "44.5", "千克")],
    )
    assert (status, ns_id) == ("split_matched", 9)


def test_merged_quantity_and_unit_differences_and_missing_rows():
    groups = compare_lines(
        [
            ns_line(1, "转印纸", "100", "张"),
            ns_line(2, "转印纸", "50", "张"),
            ns_line(3, "纹身贴纸", "350000", "个"),
            ns_line(4, "PVC卡", "10", "套"),
            ns_line(5, "墨水", "1", "瓶"),
        ],
        [
            item("01", "转印纸", "150", "张"),
            item("02", "纹身 贴纸", "350000", "套"),
            item("03", "PVC卡", "9", "套"),
            item("04", "相纸", "1", "千克"),
        ],
    )
    assert [g["status"] for g in groups] == [
        "merged",
        "unit_mismatch",
        "quantity_mismatch",
        "missing_in_ns",
        "missing_in_customs",
    ]
    assert "个" in groups[1]["note"] and "套" in groups[1]["note"]
    assert "NS 10 套，海关合计 9 套" == groups[2]["note"]


def test_declaration_level_statuses():
    items = [item("01", "相纸", "1", "千克")]
    assert compare([], items)[0] == "ns_missing"
    duplicate = [{"id": 1, "record_no": "CD1", "lines": []}, {"id": 2, "record_no": "CD2", "lines": []}]
    status, ns_id, result = compare(duplicate, items)
    assert (status, ns_id) == ("ns_duplicate", None) and "CD1、CD2" in result["note"]
    exact = [{"id": 3, "record_no": "CD3", "lines": [ns_line(1, "相纸", "1.000", "千克")]}]
    assert compare(exact, items)[0] == "matched"
    missing_qty = [{"id": 3, "record_no": "CD3", "lines": [ns_line(1, "相纸", None, "千克")]}]
    assert compare(missing_qty, items)[0] == "different"


# ---------- 文件解析 ----------


def test_parse_groups_items_by_declaration_and_normalizes_values():
    content = xlsx(
        [
            row("310120260514395336", "01", "相纸", "千克", 4315.8, "ACME LTD"),
            row("310120260514395336", 2, "相纸", "千克", "44.50000", "ACME LTD"),
            row("224420260017149355", "01", "转印纸", "张", "16,000.000", "--"),
        ]
    )
    parsed = parse("回执.xlsx", content)
    assert parsed["rows"] == 3 and "申报业务" in parsed["ignored"] and "境外收货人" in parsed["columns"]
    first, second = parsed["declarations"]
    assert first["consignee"] == "ACME LTD" and [line["item_no"] for line in first["lines"]] == ["01", "02"]
    assert first["lines"][1]["deal_quantity"] == Decimal("44.5")
    assert second["consignee"] is None and second["lines"][0]["deal_quantity"] == Decimal("16000")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row(310120260514395336, "01", "相纸", "千克", 1)], "须为文本格式"),
        (
            [row("3101202605", "01", "相纸", "千克", 1), row("3101202605", "1", "相纸", "千克", 2)],
            "项号 01 重复",
        ),
        (
            [
                row("3101202605", "01", "相纸", "千克", 1, "A"),
                row("3101202605", "02", "相纸", "千克", 2, "B"),
            ],
            "境外收货人前后不一致",
        ),
        ([row("3101202605", "01", "相纸", "", 1)], "缺少成交单位"),
        ([row("3101202605", "01", "相纸", "千克", "abc")], "成交数量不是有效数值"),
    ],
)
def test_parse_rejects_invalid_rows(rows, message):
    with pytest.raises(ApiError) as error:
        parse("回执.xlsx", xlsx(rows))
    assert message in error.value.message


def test_parse_requires_header_columns():
    with pytest.raises(ApiError) as error:
        parse("回执.xlsx", xlsx([["1"]], headers=["出口报关单号", "项号"]))
    assert "没有找到海关回执表头" in error.value.message


def test_parse_accepts_csv_with_title_row():
    lines = [
        "海关回执导出",
        ",".join(HEADERS),
        ",".join(str(v) for v in row("3101202605", "01", "相纸", "千克", 3)),
    ]
    content = base64.b64encode("\n".join(lines).encode("gb18030")).decode()
    parsed = parse("回执.csv", content)
    assert parsed["declarations"][0]["lines"][0]["deal_quantity"] == Decimal("3")


# ---------- 导入、列表、重新匹配 ----------


def _import(service, rows, filename="回执.xlsx"):
    return service.import_file(CustomsImportRequest(filename=filename, content=xlsx(rows)), "admin")


def test_import_matches_ns_declaration_and_saves_consignee(schema_engine, ns):
    engine = schema_engine
    # 来源报关单 CD870：真实报关单号 REAL870，报关行“墨水”“清洗液”各 10 个
    save(ns, engine, bundle([purchase("200", "870")], [customs("870")]))
    service = CustomsReceiptService(engine)
    result = _import(
        service,
        [
            row("REAL870", "01", "墨水", "个", 6, "ACME LTD"),
            row("REAL870", "02", "墨水", "个", 4, "ACME LTD"),
            row("REAL870", "03", "清洗液", "个", 10, "ACME LTD"),
            row("REAL999", "01", "相纸", "千克", 1, "OTHER CO"),
        ],
    )
    assert (result.created, result.replaced, result.unchanged) == (2, 0, 0)
    first, second = result.declarations
    assert (first.status, first.consignee.state) == ("split_matched", "saved")
    assert (second.status, second.consignee.state) == ("ns_missing", "pending")

    page = service.browse(CustomsReceiptQuery())
    assert page.counts.receipts == 2 and page.counts.items == 4
    assert page.counts.matched == page.counts.splitMatched == 1 and page.counts.nsMissing == 1
    receipt = next(r for r in page.items if r.declarationNo == "REAL870")
    assert receipt.nsRecordNo == "CD870" and receipt.consignee.value == "ACME LTD"
    assert [g.status for g in receipt.groups] == ["split", "matched"]
    assert [i.itemNo for i in receipt.groups[0].items] == ["01", "02"]
    assert receipt.groups[0].nsLines[0].quantity == "10" and receipt.groups[0].nsLines[0].unit == "个"

    only_missing = service.browse(CustomsReceiptQuery(status="ns_missing"))
    assert [r.declarationNo for r in only_missing.items] == ["REAL999"]
    assert only_missing.items[0].groups[0].items[0].name == "相纸"
    assert service.browse(CustomsReceiptQuery(consignee="ACME")).total == 1
    assert service.browse(CustomsReceiptQuery(name="清洗")).total == 1
    assert service.browse(CustomsReceiptQuery(declarationNo="REAL9\nNONE")).total == 1


def test_reimport_replaces_changed_content_and_keeps_unchanged(schema_engine, ns):
    engine = schema_engine
    save(ns, engine, bundle([purchase("200", "870")], [customs("870")]))
    service = CustomsReceiptService(engine)
    rows = [row("REAL870", "01", "墨水", "个", 10), row("REAL870", "02", "清洗液", "个", 10)]
    _import(service, rows)
    again = _import(service, rows)
    assert again.unchanged == 1 and again.declarations[0].status == "matched"
    changed = _import(
        service, [row("REAL870", "01", "墨水", "个", 9), row("REAL870", "02", "清洗液", "套", 10)]
    )
    assert changed.replaced == 1 and changed.declarations[0].status == "different"
    receipt = service.browse(CustomsReceiptQuery()).items[0]
    assert receipt.revision == 2 and receipt.itemCount == 2
    assert [g.status for g in receipt.groups] == ["quantity_mismatch", "unit_mismatch"]
    assert receipt.consignee.state == "empty"


def test_rematch_picks_up_ns_declaration_synced_later(schema_engine, ns):
    engine = schema_engine
    service = CustomsReceiptService(engine)
    _import(
        service,
        [row("REAL870", "01", "墨水", "个", 10, "ACME"), row("REAL870", "02", "清洗液", "个", 10, "ACME")],
    )
    assert service.browse(CustomsReceiptQuery()).items[0].status == "ns_missing"
    save(ns, engine, bundle([purchase("200", "870")], [customs("870")]))
    assert service.rematch(CustomsRematchRequest(), "admin").rematched == 1
    receipt = service.browse(CustomsReceiptQuery()).items[0]
    assert (receipt.status, receipt.consignee.state) == ("matched", "saved")
    with pytest.raises(ApiError) as error:
        service.rematch(CustomsRematchRequest(ids=[999]), "admin")
    assert error.value.status == 404


def test_service_identity_cannot_import(schema_engine):
    service = CustomsReceiptService(schema_engine)
    with pytest.raises(ApiError) as error:
        service.import_file(CustomsImportRequest(filename="a.xlsx", content=xlsx([])), "service:sync")
    assert error.value.status == 403
