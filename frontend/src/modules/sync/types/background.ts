export type Action = { allowed: boolean; reason: string };
export type AccountScope = {
  accountMode: "all" | "selected";
  accountIds: string[];
  excludedIds: string[];
  businessTypes: string[];
};
export type Plan = AccountScope & {
  revision: number;
  enabled: boolean;
  times: string[];
  lookbackDays: number;
  nextRunAt: string | null;
};
export type BackgroundConfig = {
  plan: Plan;
  submit: Action;
  pause: Action;
  coverage: string;
  businessTypeOptions: string[];
  timezone: string;
};
export type BatchInput = AccountScope & { requestId: string; startDate: string; endDate: string };
export type Batch = {
  requestId: string;
  phase: string;
  label: string;
  trigger: string;
  startDate: string;
  endDate: string;
  businessTypes: string[];
  accountMode: string;
  createdAt: string;
  finishedAt: string | null;
  message: string;
  fetched: number;
  created: number;
  updated: number;
  failed: number;
  retry: Action;
};
export type AccountResult = {
  asid: string;
  name: string;
  phase: string;
  label: string;
  counts: Record<string, number>;
  completed: number;
  total: number;
  windows: { startDate: string; endDate: string; label: string; error: string | null; requestId: string }[];
};
export type BatchDetail = Batch & {
  accounts: AccountResult[];
  poll: boolean;
  total: number;
  page: number;
  pages: number;
  pageSize: number;
};
export type BatchList = {
  plan: { enabled: boolean; nextRunAt: string | null };
  items: Batch[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Record<string, number>;
};
export const phaseOptions = [
  ["", "全部状态"],
  ["queued", "等待执行"],
  ["discovering", "查询账套"],
  ["running", "执行中"],
  ["completed", "已完成"],
  ["partial", "部分成功"],
  ["failed", "失败"],
  ["unknown", "结果待核实"],
] as const;
export const syncTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
