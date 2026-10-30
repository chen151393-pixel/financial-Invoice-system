import { http } from "../../../shared/api/http";
import type { UploadBatch } from "../types/signed-upload";

const root = "/tasks/signed-contracts/upload-jobs";
const batch = (id: string) => `${root}/${encodeURIComponent(id)}`;
export const getSignedUpload = (id: string) => http<UploadBatch>(batch(id));
export const createSignedUpload = (requestId: string, files: { filename: string; size: number }[]) =>
  http<UploadBatch>(root, "POST", { requestId, files });
export const uploadSignedChunk = (id: string, fileId: string, offset: number, content: string) =>
  http<UploadBatch>(`${batch(id)}/files/${encodeURIComponent(fileId)}/chunks`, "POST", { offset, content });
export const retrySignedUpload = (id: string, fileId: string, orderNo: string) =>
  http<UploadBatch>(`${batch(id)}/files/${encodeURIComponent(fileId)}/retry`, "POST", { orderNo });
