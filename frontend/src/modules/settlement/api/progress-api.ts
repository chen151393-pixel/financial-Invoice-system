import { http } from "../../../shared/api/http";
import type { SettlementProgress } from "../types/progress";
export const querySettlementProgress = (
  query: { consignee: string; currency: string },
  signal?: AbortSignal,
) => http<SettlementProgress>("/settlement/receivables/progress", "POST", query, signal);
