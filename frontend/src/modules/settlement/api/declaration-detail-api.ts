import { http } from "../../../shared/api/http";
import type { DeclarationDetail } from "../types/declaration-detail";

export const getDeclarationDetail = (number: string, signal?: AbortSignal) =>
  http<DeclarationDetail>(`/settlement/receivables/${encodeURIComponent(number)}`, "GET", undefined, signal);
