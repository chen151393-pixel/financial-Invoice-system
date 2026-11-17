import { http } from "../../shared/api/http";
import { readImportFile } from "../../shared/api/import-file";
import type {
  BatchDetail,
  BatchDocuments,
  BatchList,
  BatchQuery,
  BillFields,
  CandidateList,
  CandidateQuery,
  CreateBatchBody,
  GenerateContractsBody,
  Party,
  PartyBody,
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

// ---- 结汇资料：文件只读取字节后提交，格式、解析与齐全度由后端负责 ----

export const getDocuments = (batchId: number, signal?: AbortSignal) =>
  http<BatchDocuments>(`/settlement/batches/${batchId}/documents`, "GET", undefined, signal);

export async function uploadBill(batchId: number, file: File) {
  const { filename, content } = await readImportFile(file);
  return http<BatchDocuments>(`/settlement/batches/${batchId}/bills`, "POST", {
    fileName: filename,
    content,
    declarationNos: [],
  });
}

export const updateBill = (batchId: number, billId: number, body: BillFields) =>
  http<BatchDocuments>(`/settlement/batches/${batchId}/bills/${billId}`, "POST", body);

export const removeBill = (batchId: number, billId: number) =>
  http<BatchDocuments>(`/settlement/batches/${batchId}/bills/${billId}/remove`, "POST", {});

export const generateContracts = (batchId: number, body: GenerateContractsBody) =>
  http<BatchDocuments>(`/settlement/batches/${batchId}/contracts/generate`, "POST", body);

export const queryParties = (signal?: AbortSignal) =>
  http<{ items: Party[] }>("/settlement/parties/query", "POST", {}, signal);

export const saveParty = (body: PartyBody) => http<Party>("/settlement/parties", "POST", body);

export async function uploadStamp(partyId: number, file: File) {
  const { filename, content } = await readImportFile(file);
  return http<Party>(`/settlement/parties/${partyId}/stamp`, "POST", { fileName: filename, content });
}
