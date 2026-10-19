import { useEffect, useRef, useState } from "react";
import { getSyncBatch, retrySyncBatch } from "../api/background-api";
import type { BatchDetail } from "../types/background";

export function useSyncBatchDetail(id: string, page = 1) {
  const [data, setData] = useState<BatchDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const retryId = useRef({ original: id, request: crypto.randomUUID() });
  const liveId = useRef(id);
  useEffect(() => {
    let active = true;
    liveId.current = id;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await getSyncBatch(id, page);
        if (!active) return;
        setData(value);
        setError("");
        if (value.poll) timer = setTimeout(() => void load(), 3000);
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取任务失败");
      }
    }
    void load();
    return () => {
      active = false;
      liveId.current = "";
      clearTimeout(timer);
    };
  }, [id, page, attempt]);
  return {
    data: data?.requestId === id && data.page === page ? data : null,
    error,
    busy,
    refresh: () => setAttempt((value) => value + 1),
    retry: async (accept: (next: string) => void) => {
      if (retryId.current.original !== id) retryId.current = { original: id, request: crypto.randomUUID() };
      setBusy(true);
      setError("");
      try {
        const value = await retrySyncBatch(id, retryId.current.request);
        if (liveId.current === id) accept(value.requestId);
      } catch (error) {
        if (liveId.current === id)
          setError(error instanceof Error ? error.message : "提交失败，请查询原记录");
      } finally {
        if (liveId.current === id) setBusy(false);
      }
    },
  };
}
