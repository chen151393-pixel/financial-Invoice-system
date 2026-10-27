export type UploadJobFile = {
  id: string;
  filename: string;
  size: number;
  receivedBytes: number;
  status: "uploading" | "queued" | "running" | "saved" | "unmatched" | "ambiguous" | "conflict" | "failed";
  reason: string;
  orderNumber: string;
  archivePath: string | null;
  canRetry: boolean;
};

export type UploadBatch = {
  id: string;
  phase: "uploading" | "queued" | "running" | "completed";
  total: number;
  finished: number;
  saved: number;
  progressPercent: number;
  uploadPercent: number;
  message: string;
  chunkBytes: number;
  maxFileBytes: number;
  items: UploadJobFile[];
};

export const UPLOAD_STATUS: Record<UploadJobFile["status"], string> = {
  uploading: "待完成上传",
  queued: "排队中",
  running: "归档中",
  saved: "已保存",
  unmatched: "未识别单号",
  ambiguous: "匹配多个单号",
  conflict: "已有不同文件",
  failed: "未保存",
};
