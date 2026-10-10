import { http } from "../../shared/api/http";
import type { ComparisonGroup, ComparisonResult, DeclarationListQuery, PlSearchCriteria } from "./types";
import type { SourceComparisonResult } from "./source-types";
import type { InvoiceTaskDetail, InvoiceTaskList, InvoiceTaskQuery } from "./task-types";

export const listFinanceDeclarations = (criteria: DeclarationListQuery) =>
  http<ComparisonResult>("/reconciliation/declarations", "POST", criteria);

export const queryPlSourceComparison = (criteria: PlSearchCriteria) =>
  http<SourceComparisonResult>("/ns/pl-script-comparison", "POST", criteria);

export const approveDeclaration = (snapshotId: string, note: string) =>
  http<ComparisonGroup>("/reconciliation/approve", "POST", { snapshotId, note });

export const listInvoiceTasks = (query: InvoiceTaskQuery) =>
  http<InvoiceTaskList>("/reconciliation/invoice-tasks/query", "POST", query);

export const getInvoiceTask = (id: string) =>
  http<InvoiceTaskDetail>(`/reconciliation/invoice-tasks/${encodeURIComponent(id)}`);

export function prepareInvoiceTaskDocument(id: string, orderId: string) {
  return http<InvoiceTaskDetail>(
    `/reconciliation/invoice-tasks/${encodeURIComponent(id)}/documents/${encodeURIComponent(orderId)}/prepare`,
    "POST",
    {},
  );
}

export function saveTaskNotification(id: string, draft: import("./task-types").NotificationDraft) {
  return http<InvoiceTaskDetail>(
    `/reconciliation/invoice-tasks/${encodeURIComponent(id)}/notification/draft`,
    "POST",
    draft,
  );
}
export function recordTaskNotification(id: string, record: import("./task-types").NotificationRecord) {
  return http<InvoiceTaskDetail>(
    `/reconciliation/invoice-tasks/${encodeURIComponent(id)}/notification/record`,
    "POST",
    record,
  );
}
