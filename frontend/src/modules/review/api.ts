import { http } from "../../shared/api/http";
import type { ComparisonGroup, ComparisonResult, DeclarationListQuery, CurrencyEvidence } from "./types";

export const queryDeclarations = (criteria: DeclarationListQuery) =>
  http<ComparisonResult>("/review/declarations/query", "POST", criteria);

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
