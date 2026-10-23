export type TodoKind = "all" | "review" | "matching" | "task";
export type WorkbenchQuery = {
  account: string;
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
  reason: string;
  createdAt: string;
  priority: number;
  attention: boolean;
};
// unshipped：未出库报关单数（缺真实报关单号或无子采购单），不计入待办。
export type WorkbenchCounts = Record<TodoKind | "unshipped" | "reverify" | "preparation", number>;
export type Workbench = {
  generatedAt: string;
  accounts: string[];
  counts: WorkbenchCounts;
  filteredCounts: WorkbenchCounts;
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
