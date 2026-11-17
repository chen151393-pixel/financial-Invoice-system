import { useEffect, useState } from "react";
import { listSyncRecords } from "../api/history-api";
import type { SyncRecordList, SyncSource } from "../types/history";

type Filters = { page: number; phase: string; source: SyncSource };

/** 同步中心合并执行记录：后端筛选分页，每 5 秒刷新一次。 */
export function useSyncRecords() {
  const [filters, setFilters] = useState<Filters>({ page: 1, phase: "", source: "" });
  const [loaded, setLoaded] = useState<{ data: SyncRecordList; filters: Filters } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await listSyncRecords(filters.page, filters.phase, filters.source);
        if (active) {
          setLoaded({ data: value, filters });
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
  }, [filters, attempt]);
  const current = loaded?.filters === filters ? loaded.data : null;
  return {
    data: current,
    /** 计划状态在切换筛选时沿用上次结果，入口卡片不闪烁。 */
    plans: loaded?.data.plans ?? null,
    error,
    ...filters,
    refresh: () => setAttempt((value) => value + 1),
    change: (next: Partial<Filters>) => {
      setError("");
      setFilters((value) => ({ ...value, page: 1, ...next }));
    },
  };
}
