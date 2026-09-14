"""将完整NS读取结果转换为核对源行；金额仅保留十进制文本。"""

from .pl_mapper import project, reference, text

COLUMNS = [
    "报关单号",
    "申报日期",
    "关联PL单号",
    "销售单号",
    "母采购单号",
    "子采购单号",
    "货源地",
    "供应商",
    "申报公司抬头",
    "开票品名",
    "型号",
    "数量",
    "单位",
    "含税单价",
    "总金额",
]


def comparison_rows(bundle, config, pl):
    rows = []
    for kind, head_spec, line_spec in (
        ("purchases", config.purchase, config.purchase_line),
        ("customs", config.customs, config.customs_line),
    ):
        for head_id, head, lines in bundle[kind]:
            for line_id, line in lines:
                if kind == "customs" and reference(line.get(config.customs_line.pl)) != bundle["pl_id"]:
                    continue
                company_ref = (
                    head.get(config.purchase.company)
                    if kind == "purchases"
                    else line.get(config.customs_line.company)
                )
                company_id = reference(company_ref)
                company_name = text(company_ref)
                values = {**project(head, head_spec), **project(line, line_spec)}
                rows.append(
                    {
                        "source": kind,
                        "id": f"{line_spec.type}:{line_id}",
                        "headId": head_id,
                        "companyId": company_id,
                        "company": company_name or "公司未填写",
                        "currency": values.get("currency", ""),
                        "cells": [
                            values.get("declaration", ""),
                            values.get("date", ""),
                            pl,
                            values.get("sales", ""),
                            values.get("parent", ""),
                            values.get("purchase", ""),
                            values.get("origin", ""),
                            values.get("vendor", ""),
                            company_name,
                            values.get("name", ""),
                            values.get("spec", ""),
                            values.get("quantity", ""),
                            values.get("unit", ""),
                            "待确认",
                            values.get("amount", ""),
                        ],
                    }
                )
    return rows
