import { http } from "../../../shared/api/http";
import type { SyncRecordList, SyncSource } from "../types/history";

/** NS 与柠檬云发票的合并执行记录：排序（执行时间倒序）、筛选和分页均在后端完成。 */
export const listSyncRecords = (page: number, phase = "", source: SyncSource = "") => {
  const query = new URLSearchParams({ page: String(page), pageSize: "20" });
  if (phase) query.set("phase", phase);
  if (source) query.set("source", source);
  return http<SyncRecordList>(`/sync/batches?${query}`);
};
