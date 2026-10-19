"""明细待补齐的可核查原因；不将收到商品行等同于可确认匹配。"""


def detail_issue(item):
    if item["header"]["detail_status"] == "complete":
        return None
    if "Detail" not in item["payload"]:
        return (
            "本次未读取专业版商品明细，请核实服务端版本和明细读取配置"
            if item["header"]["source"] == "lemon_professional"
            else "本次来源未提供商品明细；默认版暂不支持商品明细接口"
        )
    if not item["rows"]:
        return "柠檬云明细接口返回空商品行，请在柠檬云核对原票是否包含商品明细"
    missing = []
    for key, label in (
        ("item_name", "商品名称"),
        ("unit", "单位"),
        ("quantity", "正数量"),
        ("amount_including_tax", "正含税金额"),
    ):
        if any(
            not row[key] or (key in ("quantity", "amount_including_tax") and row[key] <= 0)
            for row in item["rows"]
        ):
            missing.append(label)
    return "已收到商品行，但缺少" + "、".join(missing) + "，暂不能确认逐行匹配"


def detail_feedback(prepared, saved):
    issues = []
    for item in prepared:
        if saved[item["key"]]["detail_status"] == "complete":
            continue
        reason = detail_issue(item) or "商品行身份存在歧义，已保留原明细及分配，请人工核实"
        issues.append({"number": item["header"]["invoice_no"], "reason": reason})
    return {"detailIssues": issues[:100], "detailIssueCount": len(issues)}
