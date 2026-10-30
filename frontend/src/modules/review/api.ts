import { http } from "../../shared/api/http";
import type {
  BatchApproveResult,
  ComparisonGroup,
  ComparisonResult,
  CurrencyEvidence,
  DeclarationListQuery,
} from "./types";

export const queryDeclarations = (criteria: DeclarationListQuery) =>
  http<ComparisonResult>("/review/declarations/query", "POST", {
    ...criteria,
    createdFrom: criteria.createdFrom || null,
    createdTo: criteria.createdTo || null,
  });

// 只提交报关单身份、页面所见内容摘要与备注；后端在锁内重读来源并核对摘要。
export const approveDeclaration = (
  id: string,
  contentSha256: string,
  note: string,
  currencyEvidence: CurrencyEvidence[],
) =>
  http<ComparisonGroup>(`/review/declarations/${encodeURIComponent(id)}/approve`, "POST", {
    contentSha256,
    currencyEvidence,
    note,
  });

// 批量审核：逐张提交页面所见内容摘要；后端逐张重新核对，返回通过与跳过（含原因）的清单。
export const approveDeclarations = (groups: ComparisonGroup[], note: string) =>
  http<BatchApproveResult>("/review/declarations/approve-batch", "POST", {
    items: groups.map((group) => ({ id: group.id, contentSha256: group.contentSha256 })),
    note,
  });
