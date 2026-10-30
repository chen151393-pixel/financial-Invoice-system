import { http } from "../../../shared/api/http";
import type { NsBatchDetail, NsBatchList, NsPlan, NsPlanConfig } from "../types/ns-plan";

const root = "/sync/ns";
export const getNsPlan = () => http<NsPlanConfig>(`${root}/plan`);
export const saveNsPlan = (plan: NsPlan) =>
  http<NsPlanConfig>(`${root}/plan`, "PUT", {
    revision: plan.revision,
    enabled: plan.enabled,
    kinds: plan.kinds,
    times: plan.times,
    lookbackDays: plan.lookbackDays,
  });
export const listNsBatches = (page: number, phase = "") =>
  http<NsBatchList>(
    `${root}/batches?${new URLSearchParams({ page: String(page), pageSize: "20", ...(phase ? { phase } : {}) })}`,
  );
export const getNsBatch = (id: string, recordType: "plan" | "manual" = "plan") =>
  http<NsBatchDetail>(`${root}/batches/${encodeURIComponent(id)}?recordType=${recordType}`);
