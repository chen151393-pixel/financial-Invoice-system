"""发票行与子采购行比对、置信度（数据库设计第 5.1、5.2 节）。权重、分档、容差只在这里定义。

不一致项只降低置信度；是否允许人工通过见 allocation_policy.py。
申报价校验（2026-10-23）不计入置信度：发票不含税价格高于人民币申报价时标为异常，通过须填写说明、不能批量通过；
无法换算申报价时标为"未校验"并写明原因，不算异常。
"""

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher

from backend.core.names import normalize_name

WEIGHTS = {
    "order": 15,
    "seller": 15,
    "buyer": 10,
    "item": 15,
    "unit": 15,
    "quantity": 15,
    "amount": 15,
    "price": 0,
}
# 整单比对（发票行 ↔ 一张或多张整张子采购单合计）增加税额项，合计仍为 100。
GROUP_WEIGHTS = {
    "order": 15,
    "seller": 15,
    "buyer": 5,
    "item": 15,
    "unit": 10,
    "quantity": 15,
    "amount": 15,
    "tax": 10,
    "price": 0,
}
LABELS = {
    "tax": "税额",
    "order": "子采购单号",
    "seller": "销售方与供应商",
    "buyer": "购买方与采购公司",
    "item": "品名",
    "unit": "单位",
    "quantity": "数量",
    "amount": "含税金额",
    "price": "申报价",
}
PRICE_TOLERANCE = Decimal("0.01")
HIGH, MEDIUM = Decimal(80), Decimal(50)
AMOUNT_TOLERANCE = Decimal("0.01")
# 子采购税额按含税合计 × 税率 ÷（1 + 税率）推算，票面逐行四舍五入，允许 0.05 元差异。
TAX_TOLERANCE = Decimal("0.05")
# 供应商核心名称相似度达到该值算部分一致（须填写说明），低于则不一致。
SUPPLIER_SIMILARITY = 0.6
# 去掉的公司后缀，长的在前；“股份有限公司”去掉后不残留“股份”。
_COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "公司")
# 名称开头的地名前缀：省级简称与常见城市；以“省/市/区/县”结尾的行政区名另按规则去掉。
_PLACES = (
    "北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 海南 "
    "四川 贵州 云南 陕西 甘肃 青海 台湾 内蒙古 广西 西藏 宁夏 新疆 香港 澳门 广州 深圳 东莞 佛山 中山 珠海 惠州 "
    "江门 汕头 肇庆 揭阳 潮州 清远 韶关 湛江 茂名 汕尾 河源 梅州 阳江 云浮 杭州 宁波 温州 嘉兴 湖州 绍兴 金华 "
    "义乌 台州 丽水 衢州 舟山 南京 苏州 无锡 常州 南通 扬州 镇江 泰州 徐州 盐城 淮安 连云港 宿迁 昆山 江阴 张家港 "
    "合肥 芜湖 福州 厦门 泉州 漳州 莆田 晋江 石狮 南昌 济南 青岛 烟台 潍坊 临沂 淄博 威海 郑州 武汉 长沙 成都 "
    "西安 昆明 贵阳 南宁 海口 沈阳 大连 长春 哈尔滨 石家庄 太原 天津滨海"
).split()
_ADMIN_PREFIX = re.compile(r"^[一-鿿]{2,4}?(?:省|市|自治区|特别行政区|区|县)")
# 发票品名开头的税收分类，例如 "*计算机设备*服务器"
_TAX_PREFIX = re.compile(r"^\*[^*]*\*")


def tier(confidence):
    if confidence is None:
        return "manual"
    return "high" if confidence >= HIGH else "medium" if confidence >= MEDIUM else "low"


def text(value):
    if value is None:
        return None
    return format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)


def item_name(value):
    return normalize_name(_TAX_PREFIX.sub("", value or ""))


def name_result(invoice_name, purchase_name):
    if not invoice_name or not purchase_name:
        return "missing"
    if invoice_name == purchase_name:
        return "match"
    return "partial" if invoice_name in purchase_name or purchase_name in invoice_name else "mismatch"


def purchase_item_match(invoice_name, line):
    """商品名称和报关品名均是来源证据，取匹配程度较高的一项展示和计分。"""
    names = list(dict.fromkeys(filter(None, (line.get("item_name"), line.get("declaration_name")))))
    ranked = [(name, name_result(item_name(invoice_name), item_name(name))) for name in names]
    rank = {"match": 3, "partial": 2, "mismatch": 1, "missing": 0}
    return max(ranked, key=lambda pair: rank[pair[1]]) if ranked else (None, "missing")


def supplier_core(value):
    """去掉括号内容、公司后缀与开头地名，用于开票名称与 NS 供应商名称的模糊比较。"""
    name = normalize_name(value)
    name = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", "", name)
    for suffix in _COMPANY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    changed = True
    while changed and name:
        changed = False
        administrative = _ADMIN_PREFIX.match(name)
        if administrative and len(name) > administrative.end():
            name, changed = name[administrative.end() :], True
            continue
        for place in sorted(_PLACES, key=len, reverse=True):
            if name.startswith(place) and len(name) > len(place):
                name, changed = name[len(place) :], True
                break
    return name


def supplier_result(invoice_name, purchase_name):
    """核心名称相同或互相包含为一致；否则相似度达到阈值为部分一致（须说明），再低为不一致。"""
    left, right = supplier_core(invoice_name), supplier_core(purchase_name)
    if not left or not right:
        return "missing"
    if left == right or left in right or right in left:
        return "match"
    return "partial" if SequenceMatcher(None, left, right).ratio() >= SUPPLIER_SIMILARITY else "mismatch"


def same_unit(invoice_unit, purchase_unit_name):
    """NS 采购单位是编号，调用方须先经 source 单位字典换成名称；未知编号保留原值，不会被判为一致。"""
    return bool(
        invoice_unit
        and purchase_unit_name
        and normalize_name(invoice_unit) == normalize_name(purchase_unit_name)
    )


def order_in_remark(remark, order_no):
    """备注中出现完整订单号，不能把长单号或子单后缀误认为母单号。"""
    if not remark or not order_no:
        return False
    haystack = unicodedata.normalize("NFKC", remark).upper()
    needle = re.escape(order_number(order_no))
    if not needle:
        return False
    return re.search(rf"(?<![A-Z0-9_-]){needle}(?![A-Z0-9_-])", haystack) is not None


def order_number(value):
    """NS 引用显示名可能带记录类型；仅清理已知前缀，不截取任意文本中的单号。"""
    value = unicodedata.normalize("NFKC", value or "").strip().upper()
    return re.sub(r"^(?:采购订单|PURCHASE ORDER)\s*#\s*", "", value).strip()


def order_reference(remark, line):
    """返回备注命中的订单类型、单号；母单仅召回来源明确关联的子采购行。"""
    for kind, key in (("子采购单", "order_no"), ("母采购单", "parent_order_no")):
        if order_in_remark(remark, line.get(key)):
            return kind, order_number(line[key])
    return None


SUPPLIER_NOTE = "去掉括号内容、公司后缀和开头地名后比较；部分一致表示名称相近，须核实后填写说明"


def _check(key, invoice_value, purchase_value, result, difference=None, note="", weights=None):
    weight = (weights or WEIGHTS)[key]
    score = weight if result == "match" else Decimal(weight) / 2 if result == "partial" else 0
    return {
        "key": key,
        "label": LABELS[key],
        "invoiceValue": text(invoice_value),
        "purchaseValue": text(purchase_value),
        "result": result,
        "difference": text(difference),
        "note": note,
        "score": text(Decimal(score)),
    }


def compare(invoice, item, line, remaining_quantity, remaining_amount):
    """invoice、item 来自 invoice 门面；line 为子采购行上下文。返回 (checks, confidence)。"""
    purchase_item, item_result = purchase_item_match(item["item_name"], line)
    reference = order_reference(invoice["remark"], line)
    order_note = (
        f"备注命中{reference[0]} {reference[1]}，对应子采购单 {line['order_no']}"
        if reference
        else "备注未命中该子采购单或其母采购单"
        if invoice["remark"]
        else "发票没有备注"
    )
    unit_match = same_unit(item["unit"], line["unit_name"])
    seller = supplier_result(invoice["seller_name"], line["supplier_name"])
    checks = [
        _check(
            "order",
            invoice["remark"],
            f"{line['order_no']}（母采购单 {line['parent_order_no']}）"
            if line.get("parent_order_no")
            else line["order_no"],
            "match" if reference else "mismatch",
            note=order_note,
        ),
        _check(
            "seller",
            invoice["seller_name"],
            line["supplier_name"],
            seller,
            note="" if seller == "match" else SUPPLIER_NOTE,
        ),
        _check(
            "buyer",
            invoice["buyer_name"],
            line["company_name"],
            name_result(invoice["buyer_name_normalized"], line["company_name_normalized"]),
            note="" if invoice["buyer_name"] else "发票未提供购买方",
        ),
        _check(
            "item",
            item["item_name"],
            purchase_item,
            item_result,
        ),
        _check(
            "unit",
            item["unit"],
            line["unit"],
            "match" if unit_match else "mismatch",
            note="" if line["unit"] else "子采购单位缺失",
        ),
    ]
    checks.extend(_receipt_checks(item, unit_match, remaining_quantity, remaining_amount))
    checks.append(price_check(item, line, unit_match))
    return checks, sum(Decimal(check["score"]) for check in checks)


def _money(value):
    return format(value.quantize(PRICE_TOLERANCE), "f")


def price_check(item, line, unit_match):
    """发票不含税总价、单价不得高于报关行人民币申报价；单位一致时才比较单价。"""
    declared = line.get("declared")
    excluding = item.get("amount_excluding_tax")
    if not declared:
        return _check("price", None, None, "missing", note="未校验：子采购行没有行级报关关联")
    if declared["amount_cny"] is None:
        return _check("price", None, None, "missing", note=f"未校验：{declared['reason']}")
    if excluding is None:
        return _check("price", None, None, "missing", note="未校验：发票缺少不含税金额")
    over = (
        [f"不含税总价超出申报价 {_money(excluding - declared['amount_cny'])}"]
        if (excluding - declared["amount_cny"] > PRICE_TOLERANCE)
        else []
    )
    unit_price = None
    same_unit = unit_match and normalize_name(item["unit"] or "") == normalize_name(declared["unit"] or "")
    if same_unit and item["quantity"] and declared["unit_price_cny"] is not None:
        unit_price = excluding / item["quantity"]
        if unit_price - declared["unit_price_cny"] > PRICE_TOLERANCE:
            over.append(f"不含税单价超出申报单价 {_money(unit_price - declared['unit_price_cny'])}")
    invoice_value = f"不含税 {_money(excluding)}" + (
        f"，单价 {_money(unit_price)}" if unit_price is not None else ""
    )
    # NS 未填申报单价时单价为报关金额 ÷ 报关数量的试算值，比对结果中标注“试算”。
    estimated = "（试算）" if declared.get("unit_price_estimated") else ""
    purchase_value = f"申报 {_money(declared['amount_cny'])}" + (
        f"，单价 {_money(declared['unit_price_cny'])}{estimated}"
        if same_unit and declared["unit_price_cny"] is not None
        else ""
    )
    note = "；".join(over) if over else ("" if same_unit else "单位不一致，只比较总价")
    return _check("price", invoice_value, purchase_value, "mismatch" if over else "match", note=note)


def _receipt_checks(item, unit_match, remaining_quantity, remaining_amount):
    quantity, amount = item["quantity"], item["amount_including_tax"]
    amount_gap = amount - remaining_amount if amount is not None and remaining_amount is not None else None
    return [
        _check(
            "quantity",
            quantity,
            remaining_quantity,
            "match"
            if quantity is not None
            and remaining_quantity is not None
            and unit_match
            and 0 < quantity <= remaining_quantity
            else "mismatch",
            difference=quantity - remaining_quantity
            if quantity is not None and remaining_quantity is not None
            else None,
            note="本次数量在剩余应开范围内可分次收票；不同单位须核实换算",
        ),
        _check(
            "amount",
            amount,
            remaining_amount,
            "match"
            if amount_gap is not None and amount > 0 and amount_gap <= AMOUNT_TOLERANCE
            else "mismatch",
            difference=amount_gap,
            note="本次含税金额在剩余额度内可分次收票；收齐容差 0.01 元",
        ),
    ]
