import { useEffect, useState } from "react";
import { listNsBatches } from "../api/ns-plan-api";
import type { NsBatchList } from "../types/ns-plan";

/** NS 手动与计划执行记录：后端筛选分页，每 5 秒刷新一次。 */
export function useNsPlanBatches() {
  const [page, setPage] = useState(1);
  const [phase, setPhase] = useState("");
  const [loaded, setLoaded] = useState<{ data: NsBatchList; page: number; phase: string } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await listNsBatches(page, phase);
        if (active) {
          setLoaded({ data: value, page, phase });
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
  }, [page, phase, attempt]);
  return {
    data: loaded?.page === page && loaded.phase === phase ? loaded.data : null,
    error,
    phase,
    refresh: () => setAttempt((value) => value + 1),
    change: (next: number, nextPhase = phase) => {
      setError("");
      setPage(next);
      setPhase(nextPhase);
    },
  };
}
