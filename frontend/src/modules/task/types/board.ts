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
  grouped?: boolean;
  taskIds?: string[];
  task: TaskSummary;
  steps: TaskStep[];
  currentNode: BoardNodeKey;
  currentLabel: string;
  nextAction: string;
  blockedReason: string;
  missing: string[];
  // 能否勾选后批量登记“线下已通知”，由后端判断；提交时后端逐个任务重新校验
  notifyRecord: Capability;
  // 后端给出的实际登记范围，不能用合并卡片的完整 taskIds 替代。
  notifyTargets: NotifyBatchTarget[];
  notifyScopeRevision: string;
}

export interface NotifyBatchTarget {
  id: string;
  supplier: string;
  recordNumber: string;
  orderNumbers: string[];
}

export interface NotifyBatchGroup {
  id: string;
  scopeRevision: string;
  targets: NotifyBatchTarget[];
}

export interface NotifyGroupBatchResult {
  groups: {
    id: string;
    status: "recorded" | "skipped" | "unknown";
    taskIds: string[];
    reason: string;
  }[];
  recordedGroups: number;
  skippedGroups: number;
  unknownGroups: number;
  recordedTasks: number;
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
  groupBy?: "supplier" | "declaration";
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
