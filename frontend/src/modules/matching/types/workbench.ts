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
  // 处理方与自入库或生成起的天数（后端给出）
  role: Role;
  waitingDays: number | null;
};
export type Role = "finance" | "purchase";
export type WorkbenchCounts = Record<TodoKind | "reverify" | "preparation", number>;
// 关键指标：value 为十进制字符串（金额）或整数文本，series 为近 6 个月序列，只用于画走势线
export type Kpi = {
  key: string;
  label: string;
  role: Role;
  value: string;
  unit: string;
  currency: string;
  delta: string;
  direction: "up" | "down" | "flat";
  tone: "positive" | "warning" | "neutral";
  hint: string;
  series: string[];
};
export type FunnelStep = {
  key: string;
  label: string;
  count: number;
  // 相对上一步的通过率；第一步或上一步为 0 时为空
  rate: string | null;
  // 卡在上一步与这一步之间的报关单，key 为 pending_review 或开票跟进节点
  stuck: { key: string; label: string; count: number }[];
};
export type Workbench = {
  generatedAt: string;
  accounts: string[];
  counts: WorkbenchCounts;
  filteredCounts: WorkbenchCounts;
  noTaskCount: number;
  supplierOptions: { id: string; name: string }[];
  items: Todo[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  kpis: Kpi[];
  suppliers: {
    key: string;
    supplier: string;
    account: string;
    currency: string;
    amount: string;
    percent: string;
    longestDays: number;
    overdue: boolean;
  }[];
  unknownSupplierAmounts: number;
  // 业务流程漏斗（按报关单）与整体完结率
  funnel: { steps: FunnelStep[]; completionRate: string | null } | null;
  // 进行中开票任务按节点分布
  nodes: { total: number; nodes: { key: string; label: string; count: number; percent: string }[] } | null;
  // 应开按任务生成月；收票按全部正常人民币进项票开票月（含未匹配）；percent 为收票/应开比
  monthly: {
    month: string;
    currency: string;
    expected: string;
    received: string;
    invoiceCount: number;
    percent: string | null;
    unknownTasks: number;
  }[];
  // 待审核比对建议按置信度分档，以及比对项不一致的分类计数
  queue: {
    all: number;
    high: number;
    medium: number;
    low: number;
    anomalies: { label: string; count: number; percent: string }[];
  } | null;
  // 待通知供应商节点中、供应商未绑定企微开票群的任务汇总（前 5 家名称）
  unboundNotify: { suppliers: number; tasks: number; names: string[] } | null;
};
export const todoLabels: Record<TodoKind, string> = {
  all: "全部待办",
  review: "待核对",
  matching: "待比对 / 复核",
  task: "待开票",
};
export const roleLabels: Record<Role, string> = { finance: "财务", purchase: "采购" };
