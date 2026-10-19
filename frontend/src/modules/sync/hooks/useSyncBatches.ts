import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { listSyncBatches } from "../api/background-api";
import type { BatchList } from "../types/background";

export function useSyncBatches() {
  const [query, setQuery] = useSearchParams();
  const page = Number(query.get("page") || "1");
  const phase = query.get("phase") || "";
  const [data, setData] = useState<BatchList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await listSyncBatches(page, phase);
        if (active) {
          setData(result);
          setError("");
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取任务失败");
      } finally {
        if (active) {
          setLoading(false);
          timer = setTimeout(() => void load(), 5000);
        }
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [page, phase, attempt]);
  return {
    data,
    error,
    loading,
    phase,
    refresh: () => setAttempt((value) => value + 1),
    change: (nextPage: number, nextPhase = phase) => {
      setData(null);
      setLoading(true);
      setQuery({ page: String(nextPage), ...(nextPhase ? { phase: nextPhase } : {}) });
    },
  };
}
