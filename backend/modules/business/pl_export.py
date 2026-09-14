"""把同一次读取结果导出为XLSX，不重新查询NS、不接受浏览器回传的业务数据。"""

import base64
import re
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .pl_comparison_mapper import COLUMNS

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def xml_text(value):
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value)))


def column_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell(address, value, style=0, numeric=False):
    value = str(value)
    # Excel只有15位有效数字；更高精度按文本保留，所有业务文本均禁止解释为公式。
    digits = len(re.sub(r"[^0-9]", "", value).lstrip("0"))
    if numeric and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) and digits <= 15:
        return f'<c r="{address}" s="{style}"><v>{value}</v></c>'
    return f'<c r="{address}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml_text(value)}</t></is></c>'


def sheet_xml(rows, *, source=False):
    contents, merges = [], []
    for index, (kind, values) in enumerate(rows, 1):
        style = {"title": 1, "header": 1, "customs": 2, "purchases": 3, "group": 1}.get(kind, 0)
        if len(values) == 1:
            merges.append(f'<mergeCell ref="A{index}:{"R" if source else "O"}{index}"/>')
        cells = "".join(
            cell(
                f"{column_name(i + 1)}{index}",
                value,
                4 if kind == "data" and i == 14 else style,
                numeric=kind == "data" and i in (11, 14),
            )
            for i, value in enumerate(values)
        )
        contents.append(f'<row r="{index}" ht="36" customHeight="1">{cells}</row>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols><col min="1" max="7" width="20" customWidth="1"/><col min="8" max="9" width="30" customWidth="1"/><col min="10" max="18" width="20" customWidth="1"/></cols>
<sheetData>{"".join(contents)}</sheetData><mergeCells count="{len(merges)}">{"".join(merges)}</mergeCells></worksheet>'''


def comparison_download(result):
    context = f"账户 {result['account']} · PL {result['pl']} · 公司 {result['company'] or '全部'} · 读取时间 {result['queriedAt']}"
    main = [
        ("title", ["PL 采购报关核对"]),
        ("text", [context]),
        ("text", ["NS实时记录；金额按来源币种保留，币种及源记录见来源明细；含税单价待确认。"]),
        ("header", COLUMNS),
    ]
    source = [
        ("title", ["NS 来源明细"]),
        ("text", [context]),
        ("text", ["与合并核对来自同一次NS读取，保留源行，不按可见字段再次汇总。"]),
        ("header", [*COLUMNS, "来源", "单头内部ID", "金额币种"]),
    ]
    for group in result["groups"]:
        main.append(("group", [f"{group['pl']} / {group['company']}"]))
        for kind, label in (("customs", "报关明细"), ("purchases", "子采购订单明细")):
            main.append((kind, [label]))
            if not group[kind]:
                main.append(("text", [f"暂无{label}"]))
            for row in group[kind]:
                main.append(("data", row["cells"]))
                source.append(
                    (
                        "data",
                        [*row["cells"], f"{label} / {row['id']}", row["headId"], row["currency"] or "未返回"],
                    )
                )
    for warning in result["warnings"]:
        main.append(("text", [warning]))
    styles = f'''<styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE6EAF1"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF3FF"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEDF6F2"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="4" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    parts = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合并核对" sheetId="1" r:id="rId1"/><sheet name="来源明细" sheetId="2" r:id="rId2"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": styles,
        "xl/worksheets/sheet1.xml": sheet_xml(main),
        "xl/worksheets/sheet2.xml": sheet_xml(source, source=True),
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return {
        "filename": f"PL_{result['pl']}_采购报关核对.xlsx",
        "mediaType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "contentBase64": base64.b64encode(buffer.getvalue()).decode("ascii"),
    }
