import { http } from "../../shared/api/http";
import type { ConfirmBody, InvoiceReadiness, ResolveBody, TaskDetail, TaskList } from "./types";

export const listTasks = (query: { keyword: string; state: string; page: number; pageSize: number }) =>
  http<TaskList>(
    `/writeback/tasks?${new URLSearchParams(Object.entries(query).map(([key, value]) => [key, String(value)]))}`,
  );
export const getTask = (id: string) => http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}`);
export const refreshTask = (id: string, revision: number) =>
  http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}/refresh`, "POST", { revision });
export const confirmPlan = (id: string, body: ConfirmBody) =>
  http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}/confirm`, "POST", body);
export const confirmPreview = (id: string, revision: number) =>
  http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}/preview/confirm`, "POST", {
    revision,
    confirmScope: true,
  });
export const executeWrite = (id: string, revision: number) =>
  http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}/execute`, "POST", { revision });
export const resolveWrite = (id: string, body: ResolveBody) =>
  http<TaskDetail>(`/writeback/tasks/${encodeURIComponent(id)}/resolve`, "POST", body);
export const invoiceReadiness = (id: string) =>
  http<InvoiceReadiness>(`/writeback/invoices/${encodeURIComponent(id)}`);
export const recheckInvoice = (id: string) =>
  http<InvoiceReadiness>(`/writeback/invoices/${encodeURIComponent(id)}/recheck`, "POST");
