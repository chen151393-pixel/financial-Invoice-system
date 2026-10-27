import { useCallback, useEffect, useRef, useState } from "react";
import { readImportFile } from "../../../shared/api/import-file";
import {
  createSignedUpload,
  getSignedUpload,
  listSignedUploads,
  retrySignedUpload,
  uploadSignedChunk,
} from "../api/signed-upload";
import type { UploadBatch } from "../types/signed-upload";

/** 分片传输状态与后台队列查询；文件规则和处理结果以后端为准。 */
export function useSignedUploads() {
  const [jobs, setJobs] = useState<UploadBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [transfers, setTransfers] = useState<Record<string, string>>({});
  const mounted = useRef(true);
  const sending = useRef(false);
  const localFiles = useRef(new Map<string, File>());
  const manifests = useRef(new WeakMap<File, { id: string; files: File[] }>());

  const update = useCallback((job: UploadBatch) => {
    if (mounted.current) setJobs((current) => [job, ...current.filter((v) => v.id !== job.id)]);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const result = await listSignedUploads();
      if (mounted.current && !sending.current) {
        setJobs(result.items);
        setError("");
      }
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "任务查询失败");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!sending.current) await refresh();
      if (!stopped) timer = setTimeout(() => void poll(), 2000);
    }
    void poll();
    return () => {
      stopped = true;
      mounted.current = false;
      clearTimeout(timer);
    };
  }, [refresh]);

  async function transmit(job: UploadBatch, index: number, file: File) {
    const item = job.items[index];
    localFiles.current.set(item.id, file);
    if (item.status !== "uploading") return;
    setTransfers((v) => ({ ...v, [item.id]: "" }));
    try {
      // 重传从首片核对已有字节，防止重新选择的同名同大小文件混入旧内容。
      for (let offset = 0; offset < file.size; offset += job.chunkBytes) {
        const chunk = new File([file.slice(offset, offset + job.chunkBytes)], file.name);
        const { content } = await readImportFile(chunk);
        update(await uploadSignedChunk(job.id, item.id, offset, content));
      }
    } catch (reason) {
      if (mounted.current)
        setTransfers((v) => ({
          ...v,
          [item.id]: reason instanceof Error ? reason.message : "传输中断，请重试",
        }));
    }
  }

  async function submit(files: File[]) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      for (let offset = 0; offset < files.length; offset += 20) {
        const part = files.slice(offset, offset + 20);
        const previous = manifests.current.get(part[0]);
        const same =
          previous && previous.files.length === part.length && part.every((v, i) => v === previous.files[i]);
        const requestId = same ? previous.id : crypto.randomUUID();
        // 多批次中途失败后，重试整组选中文件也复用已创建批次。
        manifests.current.set(part[0], { id: requestId, files: part });
        const job = await createSignedUpload(
          requestId,
          part.map((file) => ({ filename: file.name, size: file.size })),
        );
        update(job);
        for (let i = 0; i < part.length; i++) await transmit(job, i, part[i]);
      }
      return true;
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "任务建立失败");
      return false;
    } finally {
      sending.current = false;
      if (mounted.current) {
        setBusy(false);
        setLoading(false);
      }
    }
  }

  async function retry(job: UploadBatch, fileId: string, orderNo: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      const file = localFiles.current.get(fileId);
      const current = await getSignedUpload(job.id);
      const index = current.items.findIndex((v) => v.id === fileId);
      if (current.items[index]?.status === "uploading" && file) await transmit(current, index, file);
      else update(await retrySignedUpload(job.id, fileId, orderNo));
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "重试失败");
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return {
    jobs,
    busy,
    loading,
    error,
    transfers,
    submit,
    retry,
    refresh,
    canResume: (id: string) => localFiles.current.has(id),
  };
}
