import { useEffect, useRef, useState } from "react";
import { exportWorkbench, queryWorkbench } from "../api/workbench-api";
import type { Workbench, WorkbenchQuery } from "../types/workbench";

export function useWorkbench() {
  const [query, setQuery] = useState<WorkbenchQuery>({
    account: "",
    keyword: "",
    kind: "all",
    sort: "priority",
    page: 1,
    pageSize: 5,
  });
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{
    data: Workbench | null;
    request: WorkbenchQuery | null;
    version: number;
    error: string;
  }>({
    data: null,
    request: null,
    version: -1,
    error: "",
  });
  const [exporting, setExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState("");
  const exportLock = useRef(false);
  useEffect(() => {
    let active = true;
    queryWorkbench(query)
      .then((data) => {
        if (active) {
          setState({ data, request: query, version, error: "" });
        }
      })
      .catch((error: unknown) => {
        if (active)
          setState({
            data: null,
            request: query,
            version,
            error: error instanceof Error ? error.message : "工作台读取失败",
          });
      });
    return () => {
      active = false;
    };
  }, [query, version]);
  const change = (patch: Partial<WorkbenchQuery>) => {
    setExportNotice("");
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  };
  async function download() {
    if (exportLock.current) return;
    exportLock.current = true;
    setExporting(true);
    setExportNotice("");
    try {
      const result = await exportWorkbench(query);
      const url = URL.createObjectURL(new Blob([result.content], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportNotice(`已导出发起时筛选的全部 ${result.count} 条待办`);
    } catch (error) {
      setExportNotice(`导出失败：${error instanceof Error ? error.message : "请重试"}`);
    } finally {
      exportLock.current = false;
      setExporting(false);
    }
  }
  const loading = state.request !== query || state.version !== version;
  return {
    data: loading ? null : state.data,
    error: loading ? "" : state.error,
    loading,
    query,
    change,
    refresh: () => {
      setExportNotice("");
      setVersion((value) => value + 1);
    },
    exporting,
    exportNotice,
    download,
  };
}
