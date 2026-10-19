import { http } from "../../shared/api/http";

export type LemonAccount = { asid: string; name: string };
export type LemonRun = {
  requestId: string;
  asid: string;
  accountName: string;
  startDate: string;
  endDate: string;
  businessTypes: string[];
  status: "running" | "completed" | "failed";
  createdAt: string;
  error: string | null;
  result: null | {
    fetched: number;
    excluded: number;
    created: number;
    updated: number;
    unchanged: number;
    pendingDetails: number;
    completeDetails?: number;
    detailIssueCount?: number;
    detailIssues?: { number: string; reason: string }[];
    saved: boolean;
    message: string;
  };
};
type Action = { allowed: boolean; reason: string };
export type LemonConfiguration = {
  query: Action;
  sync: Action;
  selected: LemonAccount | null;
  latest: LemonRun | null;
  businessTypeOptions: string[];
  defaultBusinessTypes: string[];
};
function hasBusinessTypes(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string" && item.trim())
  );
}

function incompatibleResponse(): never {
  throw new Error("同步接口缺少有效的业务类型配置，请更新并重启后端服务，再点击“刷新同步状态”");
}

function checkedRun(value: LemonRun): LemonRun {
  if (!hasBusinessTypes(value.businessTypes)) incompatibleResponse();
  return value;
}

function checkedConfiguration(value: LemonConfiguration): LemonConfiguration {
  // TypeScript 类型不会校验网络数据；旧后端缺少字段时不能进入多选组件。
  if (!hasBusinessTypes(value.businessTypeOptions) || !hasBusinessTypes(value.defaultBusinessTypes))
    incompatibleResponse();
  if (value.latest) checkedRun(value.latest);
  return value;
}

export const lemonConfiguration = () =>
  http<LemonConfiguration>("/sync/lemon/invoices/configuration").then(checkedConfiguration);
export const queryLemonAccounts = () =>
  http<{ items: LemonAccount[] }>("/sync/lemon/accounts/query", "POST", {});
export const selectLemonAccount = (asid: string) =>
  http<LemonConfiguration>("/sync/lemon/account", "POST", { asid }).then(checkedConfiguration);
export type LemonPullRequest = {
  asid: string;
  startDate: string;
  endDate: string;
  requestId: string;
  businessTypes: string[];
};
export const pullLemonInvoices = (body: LemonPullRequest) =>
  http<LemonRun>("/sync/lemon/invoices/pull-save", "POST", body).then(checkedRun);
export const getLemonRun = (requestId: string) =>
  http<LemonRun>(`/sync/lemon/runs/${encodeURIComponent(requestId)}`).then(checkedRun);
