import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { listTasks } from "../api";
import type { TaskList, TaskQuery, WritebackGroup } from "../types";

const groups: WritebackGroup[] = ["pending", "executing", "applied", "attention", "stale"];
export function readTaskQuery(params: URLSearchParams): TaskQuery {
  const group = params.get("group") as WritebackGroup;
  const page = Number(params.get("page") || 1);
  const pageSize = Number(params.get("pageSize") || 20);
  return {
    keyword: params.get("keyword") || "",
    taskNo: params.get("taskNo") || "",
    invoiceNo: params.get("invoiceNo") || "",
    supplierName: params.get("supplierName") || "",
    parentOrderNo: params.get("parentOrderNo") || "",
    state: params.get("state") || "",
    group: groups.includes(group) ? group : "",
    page: Number.isInteger(page) && page >= 1 && page <= 100000 ? page : 1,
    pageSize: [20, 50, 100].includes(pageSize) ? pageSize : 20,
  };
}

export function useWritebackList() {
  const [params, setParams] = useSearchParams();
  const query = useMemo(() => readTaskQuery(params), [params]);
  const [result, setResult] = useState<{ key: string; data: TaskList | null; error: string }>({
    key: "",
    data: null,
    error: "",
  });
  const [refresh, setRefresh] = useState(0);
  const requestKey = JSON.stringify([query, refresh]);
  const loading = result.key !== requestKey;
  const { data, error } = result;
  useEffect(() => {
    let active = true;
    void listTasks(query).then(
      (result) => {
        if (active) {
          setResult({ key: requestKey, data: result, error: "" });
        }
      },
      (reason: unknown) => {
        if (active) {
          setResult((previous) => ({
            ...previous,
            key: requestKey,
            error: reason instanceof Error ? reason.message : "任务加载失败",
          }));
        }
      },
    );
    return () => {
      active = false;
    };
  }, [query, requestKey]);
  function change(patch: Partial<TaskQuery>) {
    const next = { ...query, ...patch };
    const values = new URLSearchParams();
    if (next.keyword) values.set("keyword", next.keyword);
    for (const key of ["taskNo", "invoiceNo", "supplierName", "parentOrderNo"] as const) {
      if (next[key]) values.set(key, next[key]);
    }
    if (next.group) values.set("group", next.group);
    if (next.state) values.set("state", next.state);
    if (next.page > 1) values.set("page", String(next.page));
    if (next.pageSize !== 20) values.set("pageSize", String(next.pageSize));
    setParams(values);
    // 同一条件再次查询也应重新读取状态与计数。
    setRefresh((value) => value + 1);
  }
  function reload() {
    setRefresh((value) => value + 1);
  }
  const selected: WritebackGroup | "all" =
    query.group || data?.states?.find((state) => state.state === query.state)?.group || "all";
  return { query, data, error, loading, change, reload, selected };
}
