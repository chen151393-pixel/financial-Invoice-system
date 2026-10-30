import { useEffect, useState } from "react";
import { getNsBatch } from "../api/ns-plan-api";
import type { NsBatchDetail } from "../types/ns-plan";

/** 单个 NS 计划批次：后端标记 poll 时每 3 秒刷新，展示当前分页的真实阶段进度。 */
export function useNsPlanBatch(id: string) {
  const [data, setData] = useState<NsBatchDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await getNsBatch(id);
        if (!active) return;
        setData(value);
        setError("");
        if (value.poll) timer = setTimeout(() => void load(), 3000);
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取批次失败");
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [id, attempt]);
  return {
    data: data?.requestId === id ? data : null,
    error,
    refresh: () => setAttempt((value) => value + 1),
  };
}
