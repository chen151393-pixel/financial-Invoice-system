import { http } from "../../../shared/api/http";
import type {
  BackgroundConfig,
  Batch,
  BatchDetail,
  BatchInput,
  BatchList,
  LemonAccountOption,
  Plan,
} from "../types/background";

const root = "/sync/lemon";
export const getBackgroundConfig = () => http<BackgroundConfig>(`${root}/background/configuration`);
export const saveSyncPlan = (plan: Plan) => {
  const body = {
    revision: plan.revision,
    enabled: plan.enabled,
    times: plan.times,
    lookbackDays: plan.lookbackDays,
    accountMode: plan.accountMode,
    accountIds: plan.accountIds,
    excludedIds: plan.excludedIds,
    businessTypes: plan.businessTypes,
  };
  return http<BackgroundConfig>(`${root}/plan`, "PUT", body);
};
export const submitSyncBatch = (body: BatchInput) => http<Batch>(`${root}/batches`, "POST", body);
export const listSyncBatches = (page: number, phase: string) => {
  const query = new URLSearchParams({ page: String(page), pageSize: "20" });
  if (phase) query.set("phase", phase);
  return http<BatchList>(`${root}/batches?${query}`);
};
export const getSyncBatch = (id: string, page = 1) =>
  http<BatchDetail>(`${root}/batches/${encodeURIComponent(id)}?page=${page}`);
export const retrySyncBatch = (id: string, requestId: string) =>
  http<Batch>(`${root}/batches/${encodeURIComponent(id)}/retry`, "POST", { requestId });
export const querySyncAccounts = () =>
  http<{ items: LemonAccountOption[] }>(`${root}/accounts/query`, "POST", {});
