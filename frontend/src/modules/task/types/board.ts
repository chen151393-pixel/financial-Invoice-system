// 与后端 TaskBoard VO 一致；节点归类、计数与下一步提示均由后端给出，前端不推断。
import type { Capability, TaskStep, TaskSummary } from "./task";

export type BoardNodeKey = "documents" | "notification" | "invoices" | "comparison" | "completion" | "done";

export interface BoardNode {
  key: BoardNodeKey;
  label: string;
  hint: string;
  count: number;
}

export interface BoardItem {
  task: TaskSummary;
  steps: TaskStep[];
  currentNode: BoardNodeKey;
  currentLabel: string;
  nextAction: string;
  blockedReason: string;
  missing: string[];
  // 能否勾选后批量登记“线下已通知”，由后端判断；提交时后端逐个任务重新校验
  notifyRecord: Capability;
}

// 批量登记线下已通知的逐任务结果；skipped 附后端给出的原因
export interface NotifyBatchResult {
  recorded: { id: string; reason: string }[];
  skipped: { id: string; reason: string }[];
}

export interface TaskBoard {
  nodes: BoardNode[];
  openTotal: number;
  items: BoardItem[];
  suppliers: { id: string; name: string }[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

export interface TaskBoardQuery {
  // 兼容发票工作台和旧跟进链接的报关单范围，由后端校验和筛选。
  stage?: string;
  createdFrom?: string;
  createdTo?: string;
  keyword: string;
  supplierName?: string;
  recordNo?: string;
  purchaseOrderNo?: string;
  supplierId: string;
  // 空为全部进行中的任务
  node: "" | BoardNodeKey;
  page: number;
  pageSize: number;
}
