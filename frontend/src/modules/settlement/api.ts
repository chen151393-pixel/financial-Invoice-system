import { http } from "../../shared/api/http";
import type {
  BatchDetail,
  BatchList,
  BatchQuery,
  CandidateList,
  CandidateQuery,
  CreateBatchBody,
  RemittanceBody,
} from "./types";

// 结汇接口：路径判定、金额核对与可操作判断全部在后端，前端只提交输入并展示结果。
export const queryCandidates = (query: CandidateQuery, signal?: AbortSignal) =>
  http<CandidateList>("/settlement/candidates/query", "POST", query, signal);

export const queryBatches = (query: BatchQuery, signal?: AbortSignal) =>
  http<BatchList>("/settlement/batches/query", "POST", query, signal);

export const getBatch = (id: number, signal?: AbortSignal) =>
  http<BatchDetail>(`/settlement/batches/${id}`, "GET", undefined, signal);

export const createBatch = (body: CreateBatchBody) => http<BatchDetail>("/settlement/batches", "POST", body);

export const markDocumentsReady = (id: number) =>
  http<BatchDetail>(`/settlement/batches/${id}/documents-ready`, "POST", {});

export const recordRemittance = (id: number, body: RemittanceBody) =>
  http<BatchDetail>(`/settlement/batches/${id}/remittance`, "POST", body);

export const settleBatch = (id: number) => http<BatchDetail>(`/settlement/batches/${id}/settle`, "POST", {});

export const cancelBatch = (id: number, reason: string) =>
  http<BatchDetail>(`/settlement/batches/${id}/cancel`, "POST", { reason });
