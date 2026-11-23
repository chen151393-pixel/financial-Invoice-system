import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { exportRecovery, queryRecovery } from "../api/recovery";
import type { RecoveryBoard, RecoveryQuery } from "../types/recovery";
import { readRecoveryQuery, writeRecoveryQuery } from "./recovery-query";

interface Loaded {
  // 已完成的请求（地址条件 + 刷新次数）；与当前请求不同即为加载中，保留上一份数据避免页面跳动
  request: string;
  data: RecoveryBoard | null;
  error: string;
}
type State =
  | { kind: "loading"; data: RecoveryBoard | null }
  | { kind: "error"; message: string; data: RecoveryBoard | null }
  | { kind: "ready"; data: RecoveryBoard };

const message = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);

/** 看板查询放在地址中，刷新与分享链接保持同一条件。 */
export function useRecoveryBoard() {
  const [params, setParams] = useSearchParams();
  const query = readRecoveryQuery(params);
  const key = params.toString();
  const [refresh, setRefresh] = useState(0);
  const request = `${key}#${refresh}`;
  const [loaded, setLoaded] = useState<Loaded>({ request: "", data: null, error: "" });
  const [exporting, setExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void queryRecovery(readRecoveryQuery(new URLSearchParams(key)), controller.signal)
      .then((data) => {
        if (active) setLoaded({ request: `${key}#${refresh}`, data, error: "" });
      })
      .catch((error: unknown) => {
        if (active)
          setLoaded((current) => ({
            request: `${key}#${refresh}`,
            data: current.data,
            error: message(error, "应收看板读取失败"),
          }));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [key, refresh]);
  const state: State =
    loaded.request !== request
      ? { kind: "loading", data: loaded.data }
      : loaded.error
        ? { kind: "error", message: loaded.error, data: loaded.data }
        : loaded.data
          ? { kind: "ready", data: loaded.data }
          : { kind: "loading", data: null };

  function search(next: RecoveryQuery) {
    setParams(writeRecoveryQuery(next));
  }

  async function download() {
    if (exporting) return;
    setExporting(true);
    setExportNotice("");
    try {
      const result = await exportRecovery({ ...query, page: 1 });
      const url = URL.createObjectURL(new Blob([result.content], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportNotice(`已导出当前条件下的全部 ${result.count} 个任务`);
    } catch (error) {
      setExportNotice(`导出失败：${message(error, "请稍后重试")}`);
    } finally {
      setExporting(false);
    }
  }

  return {
    state,
    query,
    search,
    reload: () => setRefresh((value) => value + 1),
    download,
    exporting,
    exportNotice,
  };
}
