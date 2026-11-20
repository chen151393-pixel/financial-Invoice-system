import { http } from "../../../shared/api/http";
import type { DirectDocumentQuery } from "../types";
import type { DocumentGroup, DocumentGroupList, GroupBasisPreview } from "../types/document-group";

export const queryDocumentGroups = (query: DirectDocumentQuery, signal?: AbortSignal) =>
  http<DocumentGroupList>("/settlement/direct-document-groups/query", "POST", query, signal);
export const getDocumentGroup = (id: number, signal?: AbortSignal) =>
  http<DocumentGroup>(`/settlement/direct-document-groups/${id}`, "GET", undefined, signal);
export const createDocumentGroup = (requestId: string, declarationNos: string[]) =>
  http<DocumentGroup>("/settlement/direct-document-groups", "POST", { requestId, declarationNos });

export const ensureSingleDocumentGroup = (declarationNo: string, signal?: AbortSignal) =>
  http<DocumentGroup>("/settlement/direct-document-groups/single", "POST", { declarationNo }, signal);

export const previewGroupBasis = (id: number, signal?: AbortSignal) =>
  http<GroupBasisPreview>(
    `/settlement/direct-document-groups/${id}/source-preview`,
    "GET",
    undefined,
    signal,
  );
export const confirmGroupBasis = (id: number, token: string) =>
  http<DocumentGroup>(`/settlement/direct-document-groups/${id}/source`, "POST", { token });
