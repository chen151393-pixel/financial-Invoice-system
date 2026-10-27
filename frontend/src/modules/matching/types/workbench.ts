export type TodoKind = "all" | "review" | "matching" | "task";
export type WorkbenchQuery = {
  account: string;
  // 供应商与报关单创建日期（YYYY-MM-DD，须同时填写）；空为不限
  supplierId: string;
  createdFrom: string;
  createdTo: string;
  keyword: string;
  kind: TodoKind;
  sort: "priority" | "oldest" | "newest";
  page: number;
  pageSize: number;
  trendStart?: string | null;
  trendEnd?: string | null;
};
export type Todo = {
  key: string;
  kind: Exclude<TodoKind, "all">;
  targetId: string;
  title: string;
  subtitle: string;
  party: string;
  account: string;
  amount: string | null;
  currency: string;
  amountLabel: string;
  statusLabel: string;
  stage?: string;
  stageLabel?: string;
  reason: string;
  createdAt: string;
  priority: number;
  attention: boolean;
};
export type WorkbenchCounts = Record<TodoKind | "reverify" | "preparation", number>;
export type Workbench = {
  generatedAt: string;
  accounts: string[];
  counts: WorkbenchCounts;
  filteredCounts: WorkbenchCounts;
  // 业务状态分区（按报关单计数）
  stages: {
    key: "pending_review" | "notify" | "invoicing" | "documents" | "completed";
    label: string;
    count: number;
  }[];
  noTaskCount: number;
  supplierOptions: { id: string; name: string }[];
  items: Todo[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  month: {
    month: string;
    total: number;
    completed: number;
    percent: string | null;
    received: { currency: string; amount: string | null }[];
  };
  suppliers: {
    key: string;
    supplier: string;
    account: string;
    currency: string;
    amount: string;
    percent: string;
  }[];
  unknownSupplierAmounts: number;
  trendStart: string;
  trendEnd: string;
  latestInvoiceDate: string | null;
  // 业务流程漏斗（后端由业务状态累加，rate 为相对上一步的通过率）
  funnel: { key: string; label: string; count: number; rate: string | null }[];
  // 按任务生成月份的人民币应开与目前已收票金额（最近 6 个月）
  monthly: {
    month: string;
    currency: string;
    expected: string;
    received: string;
    percent: string | null;
    unknownTasks: number;
  }[];
  // 待审核比对建议按置信度分档
  queue: { all: number; high: number; medium: number; low: number } | null;
  trend: {
    currency: string;
    hasNegative: boolean;
    points: { date: string; amount: string | null; percent: string; negative: boolean }[];
  }[];
};
export const todoLabels: Record<TodoKind, string> = {
  all: "全部待办",
  review: "待核对",
  matching: "待比对 / 复核",
  task: "待开票",
};
