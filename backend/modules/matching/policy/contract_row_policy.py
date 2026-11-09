"""NS 子采购合同的行合并口径：供应商按合同开票，发票行对应合同行，而不是 NS 子采购明细。

2026-11-09 只读核实 NS 子采购单 YE-YH20260804-P250-1：11 条明细的报关品名为 10 条“PVC膜”、1 条“pvc膜”，
报关单位均为“卷”，单价有 3.72、5.40、7.44 三种。NS 合同合并为两行：“PVC膜”6408 卷、26055.36，
“pvc膜”648 卷、4822.42，单价 = 合计金额 ÷ 数量。由此确定合并键为报关品名 + 单位：
- 报关品名原样比较（区分大小写、不做全半角或税收分类规范化），与 NS 合同一致；报关品名为空时退回商品名称；
- 单价不参与合并；
- 合同的“型号”“包装方式”在样本中为空，是否参与合并须取得 NS 合同脚本后再核实，当前不纳入。
"""


def contract_key(line):
    """合同行合并键 (品名, 单位)；line 为 source 门面的子采购行上下文。"""
    name = (line.get("declaration_name") or line.get("item_name") or "").strip()
    return name, (line.get("unit_name") or "").strip()


def contract_rows(lines):
    """把 {子采购行 ID: 上下文} 按合同口径分组，返回 [[子采购行 ID, ...]]，组与组内均保持原顺序。"""
    rows = {}
    for line_id, line in lines.items():
        rows.setdefault(contract_key(line), []).append(line_id)
    return list(rows.values())
