import { useEffect, useState } from "react";
import { listNsBatches } from "../api/ns-plan-api";
import type { NsBatchList } from "../types/ns-plan";

/** NS 计划执行记录：后端分页，每 5 秒刷新一次以展示后台进度。 */
export function useNsPlanBatches() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NsBatchList | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await listNsBatches(page);
        if (active) {
          setData(value);
          setError("");
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取执行记录失败");
      } finally {
        if (active) timer = setTimeout(() => void load(), 5000);
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [page, attempt]);
  return {
    data: data?.page === page ? data : null,
    error,
    refresh: () => setAttempt((value) => value + 1),
    change: (next: number) => setPage(next),
  };
}
