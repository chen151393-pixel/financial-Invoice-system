import { useEffect, useState } from "react";
import { isNotConnected, listWriteback } from "../api";
import type { WritebackList, WritebackQuery } from "../types";

export type ListStatus = "loading" | "ready" | "error" | "notConnected";

/** 按提交的查询条件读取回写列表；条件变化后忽略旧响应，避免旧结果覆盖新条件。 */
export function useWritebackList(query: WritebackQuery) {
  const [result, setResult] = useState<{ key: string; data: WritebackList | null; error: string }>({
    key: "",
    data: null,
    error: "",
  });
  const [notConnected, setNotConnected] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const params = JSON.stringify(query);
  const key = `${params}#${attempt}`;
  useEffect(() => {
    let active = true;
    listWriteback(JSON.parse(params) as WritebackQuery)
      .then((data) => {
        if (!active) return;
        setNotConnected(false);
        setResult({ key, data, error: "" });
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (isNotConnected(error)) {
          setNotConnected(true);
          setResult({ key, data: null, error: "" });
          return;
        }
        setResult({ key, data: null, error: error instanceof Error ? error.message : "读取回写列表失败" });
      });
    return () => {
      active = false;
    };
  }, [params, key]);
  const current = result.key === key;
  const status: ListStatus = notConnected
    ? "notConnected"
    : !current
      ? "loading"
      : result.error
        ? "error"
        : "ready";
  return {
    status,
    data: current ? result.data : null,
    error: current ? result.error : "",
    refresh: () => setAttempt((value) => value + 1),
  };
}
