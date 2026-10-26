// 与后端 TaskBoard VO 一致；节点归类、计数与下一步提示均由后端给出，前端不推断。
import type { TaskStep, TaskSummary } from "./task";

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
  keyword: string;
  supplierId: string;
  // 空为全部进行中的任务
  node: "" | BoardNodeKey;
  page: number;
  pageSize: number;
}
