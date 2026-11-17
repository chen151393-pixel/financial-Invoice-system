"""销售合同 PDF 渲染：版式与条款来自 templates/sales_contract.json，数据由调用方给出，不读数据库。

中文字体：配置了 SETTLEMENT_PDF_FONT（TTF 路径）时嵌入该字体；否则使用 PDF 内置的 STSong-Light（不嵌入）。
"""

import io
import json
import re
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.core.errors import ApiError

from ..policy.amount_policy import money
from ..policy.bill_parse_policy import english_date

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "sales_contract.json"
STAMP_SIZE = 34 * mm


@lru_cache(maxsize=1)
def template():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _font(path):
    if path:
        try:
            pdfmetrics.registerFont(TTFont("SettlementCJK", str(path)))
        except (TTFError, OSError):
            raise ApiError(503, "销售合同字体文件无法读取，请检查 SETTLEMENT_PDF_FONT") from None
        return "SettlementCJK"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


# 汉字、全角标点等用中文字体，其余（英文、数字、半角标点）用西文字体
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f\u2010-\u2027\u2030-\u205e]+")


def _markup(text, latin_font):
    """转义并按字符类别切换字体：PDF 内置中文字体的英文字形间距不可靠，英文改用西文字体。"""
    text = str(text)
    if not latin_font:
        return escape(text)
    parts, position = [], 0
    for match in _CJK.finditer(text):
        if match.start() > position:
            parts.append(f'<font name="{latin_font}">{escape(text[position : match.start()])}</font>')
        parts.append(escape(match.group()))
        position = match.end()
    if position < len(text):
        parts.append(f'<font name="{latin_font}">{escape(text[position:])}</font>')
    return "".join(parts)


def _number(value):
    """数量按原值展示，去掉无意义的尾零。"""
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def _price(value):
    """单价至少两位小数，最多四位。"""
    text = _number(value)
    whole, _, fraction = text.partition(".")
    return f"{whole}.{fraction.ljust(2, '0')}"


def render(contract, buyer, seller, terms, currency, stamps, *, font_path=None):
    """返回 PDF 字节。stamps 为 {"buyer": 图片路径或 None, "seller": 图片路径或 None}。"""
    font = _font(str(font_path) if font_path else "")
    body = ParagraphStyle("body", fontName=font, fontSize=9, leading=13, wordWrap="CJK")
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.8)
    title = ParagraphStyle("title", parent=body, fontSize=15, leading=20, alignment=1)

    # 嵌入了 TTF 时整篇用该字体；否则英文、数字用 Helvetica
    latin = "" if font_path else "Helvetica"

    def p(text, style=body):
        return Paragraph(_markup(text, latin), style)

    doc = template()
    filled = {
        **terms,
        "port_of_loading": contract["port_of_loading"],
        "port_of_destination": contract["port_of_destination"],
        "shipment_before": contract["on_board_date"].isoformat() if contract["on_board_date"] else "",
    }
    width = A4[0] - 30 * mm
    half = width / 2
    story = [p(doc["title"], title), Spacer(1, 3 * mm)]
    heads = [
        (
            f"合同编号(Contract No.): {contract['contract_no']}",
            f"签订日期(Date): {english_date(contract['contract_date'])}",
        ),
        (f"买方：{buyer['name_cn'] or buyer['name_en']}", f"卖方：{seller['name_cn'] or seller['name_en']}"),
        (f"The Buyer: {buyer['name_en']}", f"The Seller: {seller['name_en']}"),
        (f"地址：{buyer['address_cn'] or ''}", f"地址：{seller['address_cn'] or ''}"),
        (f"Address: {buyer['address_en']}", f"Address: {seller['address_en']}"),
        (f"电话(Tel)：{buyer['phone'] or ''}", f"电话(Tel)：{seller['phone'] or ''}"),
    ]
    head_table = Table([[p(left), p(right)] for left, right in heads], colWidths=[half, half])
    head_table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1)])
    )
    story += [head_table, Spacer(1, 3 * mm), p(doc["preamble"]), Spacer(1, 2 * mm)]

    rows = [
        [
            p(text, small)
            for text in (
                "S/N",
                "Commodity & Specification",
                "Quantity",
                "Unit",
                f"Price {currency}/Unit",
                f"Amount {currency}",
            )
        ]
    ]
    for line in contract["lines"]:
        name = f"{line['name']} {line['specification']}".strip()
        price = "" if line["unit_price"] is None else _price(line["unit_price"])
        rows.append(
            [
                p(text, small)
                for text in (
                    line["seq"],
                    name,
                    _number(line["quantity"]),
                    line["unit"],
                    price,
                    money(line["amount"]),
                )
            ]
        )
    rows.append([p(text, small) for text in ("", "Intotal", "", "", "", money(contract["amount"]))])
    goods = Table(rows, colWidths=[w * width for w in (0.07, 0.4, 0.12, 0.09, 0.17, 0.15)], repeatRows=1)
    goods.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ]
        )
    )
    story += [goods, Spacer(1, 3 * mm)]
    story += [p(clause.format(**filled), small) for clause in doc["clauses"]]

    def stamp(path):
        return (
            Image(str(path), width=STAMP_SIZE, height=STAMP_SIZE, mask="auto")
            if path
            else Spacer(1, STAMP_SIZE)
        )

    signature = Table(
        [
            [p("买方代表（签字）："), p("卖方代表（签字）：")],
            [p("Representative of the Buyer:"), p("Representative of the Seller:")],
            [p("(Authorized signature):"), p("(Authorized signature):")],
            [stamp(stamps.get("buyer")), stamp(stamps.get("seller"))],
        ],
        colWidths=[half, half],
    )
    signature.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 3), (-1, 3), "LEFT")]))
    # 签字栏与印章不跨页拆开
    story += [Spacer(1, 3 * mm), KeepTogether([signature])]

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"销售合同 {contract['contract_no']}",
    ).build(story)
    return buffer.getvalue()
