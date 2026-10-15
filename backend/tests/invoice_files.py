"""测试用柠檬云合并表 XLSX（内存生成，虚构数据）。"""

import base64
from decimal import Decimal
from io import BytesIO

from backend.modules.invoice.service.excel_parser import HEADERS, LINE_HEADERS
from openpyxl import Workbook


def invoice(
    number, lines, *, seller="上海 供应商（有限）公司", remark="", status="正常", business="采购固定资产"
):
    """lines：[(品名, 单位, 数量, 不含税金额, 税额)]，金额为字符串。"""
    return {
        "number": number,
        "seller": seller,
        "remark": remark,
        "status": status,
        "business": business,
        "lines": lines,
    }


def workbook(invoices):
    """返回 base64 编码的 XLSX 内容（34 列票头商品合并表）。"""
    book = Workbook()
    sheet = book.active
    sheet.title = "发票明细"
    sheet.append(HEADERS + LINE_HEADERS[4:])
    for value in invoices:
        net = sum(Decimal(line[3]) for line in value["lines"])
        tax = sum(Decimal(line[4]) for line in value["lines"])
        head = {
            "发票种类": "数电发票（增值税专用发票）",
            "开票日期": "2026-10-10",
            "发票号码": value["number"],
            "发票状态": value["status"],
            "供应商名称": value["seller"],
            "纳税人识别号": "91310000TEST00001X",
            "业务类型": value["business"],
            "合计金额": format(net, "f"),
            "税率": "13%",
            "合计税额": format(tax, "f"),
            "价税合计": format(net + tax, "f"),
            "备注": value["remark"] or None,
        }
        for name, unit, quantity, line_net, line_tax in value["lines"]:
            detail = [name, None, unit, quantity, line_net, "13%", line_tax, None, None, None, None]
            sheet.append([head.get(column) for column in HEADERS] + detail)
    output = BytesIO()
    book.save(output)
    return base64.b64encode(output.getvalue()).decode()
