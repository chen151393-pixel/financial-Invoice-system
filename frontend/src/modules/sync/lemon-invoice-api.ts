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
export const lemonConfiguration = () => http<LemonConfiguration>("/sync/lemon/invoices/configuration");
export const queryLemonAccounts = () =>
  http<{ items: LemonAccount[] }>("/sync/lemon/accounts/query", "POST", {});
export const selectLemonAccount = (asid: string) =>
  http<LemonConfiguration>("/sync/lemon/account", "POST", { asid });
export type LemonPullRequest = {
  asid: string;
  startDate: string;
  endDate: string;
  requestId: string;
  businessTypes: string[];
};
export const pullLemonInvoices = (body: LemonPullRequest) =>
  http<LemonRun>("/sync/lemon/invoices/pull-save", "POST", body);
export const getLemonRun = (requestId: string) =>
  http<LemonRun>(`/sync/lemon/runs/${encodeURIComponent(requestId)}`);
