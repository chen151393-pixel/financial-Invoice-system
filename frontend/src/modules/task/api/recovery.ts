import { http } from "../../../shared/api/http";
import type { RecoveryBoard, RecoveryExport, RecoveryQuery } from "../types/recovery";

export const queryRecovery = (query: RecoveryQuery, signal?: AbortSignal) =>
  http<RecoveryBoard>("/task/recovery/query", "POST", query, signal);

export const exportRecovery = (query: RecoveryQuery) =>
  http<RecoveryExport>("/task/recovery/export", "POST", query);
