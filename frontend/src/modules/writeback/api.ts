import { HttpError, http } from "../../shared/api/http";
import type { WritebackList, WritebackQuery, WritebackRequest } from "./types";

const root = "/writeback";

/**
 * 后端未登记的接口统一返回 404“接口不存在”或 405；据此显示“尚未接入”，
 * 与业务上的“记录不存在”（带具体中文原因）区分，不把未接入当成空数据。
 */
export function isNotConnected(error: unknown) {
  return (
    error instanceof HttpError &&
    ((error.status === 404 && error.message === "接口不存在") || error.status === 405)
  );
}

export function listWriteback(query: WritebackQuery) {
  const params = new URLSearchParams({ page: String(query.page), pageSize: String(query.pageSize) });
  for (const key of ["phase", "vendor", "invoiceNo", "dateFrom", "dateTo"] as const) {
    if (query[key]) params.set(key, query[key]);
  }
  return http<WritebackList>(`${root}/invoices?${params}`);
}

/** 生成不可变预览；requestId 由调用方保留，网络中断后重发不会生成第二份预览。 */
export const createPreview = (invoiceId: string, requestId: string) =>
  http<WritebackRequest>(`${root}/previews`, "POST", { invoiceId, requestId });

export const getWritebackRequest = (requestId: string) =>
  http<WritebackRequest>(`${root}/requests/${encodeURIComponent(requestId)}`);

/** 确认执行：后端重新校验写入开关、预览有效期与账单锁；前端不判断能否写入。 */
export const executeWriteback = (requestId: string) =>
  http<WritebackRequest>(`${root}/requests/${encodeURIComponent(requestId)}/execute`, "POST", {
    confirm: true,
  });

/** 结果待核实时按请求编号查询 NS，不重新提交。 */
export const verifyWriteback = (requestId: string) =>
  http<WritebackRequest>(`${root}/requests/${encodeURIComponent(requestId)}/verify`, "POST", {});
