import type { Bill } from "./types";

// 候选账单展示用文字：名称由后端按审核快照与 NS 查询结果补齐；取不到时说明原因，不回退显示 NS 内部 ID。
export const parentLabel = (number: string) => number || "母采购单号未取得";

export const subsidiaryLabel = (name: string) => name || "子公司不是本票采购公司";

// NS 账单的子采购单字段为空时无法精确对应，须按母单人工确认归属
export const subPurchaseLabel = (bill: Pick<Bill, "subPurchaseOrderId" | "subPurchaseOrderNo">) =>
  bill.subPurchaseOrderId ? bill.subPurchaseOrderNo || "非本票子采购单" : "NS 账单未填子采购单";
