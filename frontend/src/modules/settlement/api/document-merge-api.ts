import { HttpError, http } from "../../../shared/api/http";
import type {
  ConfirmMerge,
  DocumentMergeQuery,
  MergeCandidates,
  MergePreview,
  MergeSelection,
} from "../types/document-merge";
import type { DocumentGroup } from "../types/document-group";
export const queryDocumentMerge = (body: DocumentMergeQuery, signal?: AbortSignal) =>
  http<MergeCandidates>("/settlement/direct-document-groups/merge/query", "POST", body, signal);
export const previewDocumentMerge = (body: MergeSelection, signal?: AbortSignal) =>
  http<MergePreview>("/settlement/direct-document-groups/merge/preview", "POST", body, signal);
export const confirmDocumentMerge = (body: ConfirmMerge) =>
  http<DocumentGroup>("/settlement/direct-document-groups/merge", "POST", body);

export const getDocumentMergeResult = (requestId: string) =>
  http<{ group: DocumentGroup | null }>(
    `/settlement/direct-document-groups/merge/requests/${encodeURIComponent(requestId)}`,
  );

export class MergeResultUnknown extends Error {}

/** 响应丢失先查原请求；查询也未能确认时，保留原请求供幂等重试。 */
export async function confirmDocumentMergeRecovering(body: ConfirmMerge): Promise<DocumentGroup> {
  try {
    return await confirmDocumentMerge(body);
  } catch (reason) {
    if (reason instanceof HttpError && reason.status < 500) throw reason;
    try {
      const result = await getDocumentMergeResult(body.requestId);
      if (result.group) return result.group;
    } catch {
      throw new MergeResultUnknown(
        "暂时无法确认合并结果，请按原请求重试；系统会复用同一请求，避免重复创建。",
      );
    }
    throw new MergeResultUnknown("尚未查到已完成的合并结果，请按原请求重试。");
  }
}
