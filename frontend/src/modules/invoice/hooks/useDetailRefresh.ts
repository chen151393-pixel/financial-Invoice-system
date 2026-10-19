import { useEffect, useRef, useState } from "react";
import { HttpError } from "../../../shared/api/http";
import { getDetailActions, getDetailRun, refreshInvoiceDetails } from "../api/detail-refresh";
import type { DetailAction, DetailRun } from "../api/detail-refresh";

const STORAGE_KEY = "invoice-detail-refresh-request";
export function useDetailRefresh(ids: string[], onSaved: () => void) {
  const scope = ids.join(",");
  const [permissions, setPermissions] = useState<{ scope: string; rows: DetailAction[] } | null>(null);
  const [selection, setSelection] = useState<{ scope: string; ids: string[] }>({ scope, ids: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [run, setRun] = useState<DetailRun | null>(null);
  const [pending, setPending] = useState(() => sessionStorage.getItem(STORAGE_KEY) ?? "");
  const [version, setVersion] = useState(0);
  const locked = useRef(false);
  const mounted = useRef(true);
  const saved = useRef(onSaved);
  useEffect(() => {
    saved.current = onSaved;
  }, [onSaved]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    if (scope)
      void getDetailActions(scope.split(","))
        .then((data) => {
          if (!active) return;
          setPermissions({ scope, rows: data.rows });
          if (data.latest?.status === "running") setRun(data.latest);
        })
        .catch((cause: unknown) => {
          if (active) setError(cause instanceof Error ? cause.message : "补拉权限读取失败");
        });
    return () => {
      active = false;
    };
  }, [scope, version]);
  const actions = Object.fromEntries(
    (permissions?.scope === scope ? permissions.rows : []).map((row) => [row.invoiceId, row]),
  );
  const selected = selection.scope === scope ? selection.ids : [];
  function select(id: string, checked: boolean) {
    setSelection({ scope, ids: checked ? [...selected, id] : selected.filter((value) => value !== id) });
  }
  function accept(result: DetailRun) {
    setRun(result);
    if (result.status !== "running") {
      sessionStorage.removeItem(STORAGE_KEY);
      setPending("");
      setSelection({ scope, ids: [] });
      setPermissions(null);
      setVersion((value) => value + 1);
      if (result.status === "completed") saved.current();
    }
  }
  async function execute(invoiceIds?: string[]) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    let requestId = pending || (run?.status === "running" ? run.requestId : "");
    try {
      if (requestId) {
        const result = await getDetailRun(requestId);
        if (mounted.current) accept(result);
      } else if (invoiceIds) {
        requestId = crypto.randomUUID();
        sessionStorage.setItem(STORAGE_KEY, requestId);
        setPending(requestId);
        const result = await refreshInvoiceDetails(invoiceIds, requestId);
        if (mounted.current) accept(result);
      } else {
        setPermissions(null);
        setVersion((value) => value + 1);
      }
    } catch (cause) {
      if (!mounted.current) return;
      setError(cause instanceof Error ? cause.message : "补拉失败，请查询原请求结果");
      // 明确的请求拒绝可重新选择；网络或服务异常只查询原请求，不自动重发。
      if (invoiceIds && cause instanceof HttpError && cause.status < 500) {
        sessionStorage.removeItem(STORAGE_KEY);
        setPending("");
      } else if (requestId) {
        try {
          const result = await getDetailRun(requestId);
          if (mounted.current) accept(result);
        } catch {
          /* 原请求仍待核实，保留编号和查询入口。 */
        }
      }
    } finally {
      locked.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return {
    actions,
    selected,
    select,
    clearSelection: () => setSelection({ scope: "", ids: [] }),
    selectAll: (checked: boolean) =>
      setSelection({ scope, ids: checked ? ids.filter((id) => actions[id]?.allowed) : [] }),
    busy,
    error,
    run,
    pending,
    blocked: busy || Boolean(pending) || run?.status === "running",
    execute,
  };
}
