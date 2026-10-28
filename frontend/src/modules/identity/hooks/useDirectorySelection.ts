import { useCallback, useEffect, useRef, useState } from "react";
import { confirmDirectory, planDirectory, previewDirectory, queryDirectoryMembers } from "../api";
import type {
  DirectoryMembers,
  DirectoryPlan,
  DirectoryPreview,
  DirectorySelection,
  SyncRun,
} from "../types";

const message = (e: unknown) => (e instanceof Error ? e.message : "飞书组织读取失败");
const empty: DirectorySelection = { departmentIds: [], userIds: [] };

/** 只维护选择和请求状态，人数、继承范围及导入结果均来自后端。 */
export function useDirectorySelection(onDone: () => Promise<void>) {
  const [preview, setPreview] = useState<DirectoryPreview | null>(null);
  const [selection, setSelection] = useState<DirectorySelection>(empty);
  const [department, setDepartment] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [members, setMembers] = useState<DirectoryMembers | null>(null);
  const [plan, setPlan] = useState<DirectoryPlan | null>(null);
  const [result, setResult] = useState<SyncRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const [memberError, setMemberError] = useState("");
  const [retry, setRetry] = useState(0);
  const request = useRef(0);
  const fetching = useRef(false);

  const acceptPreview = useCallback((value: DirectoryPreview) => {
    request.current++;
    setMembers(null);
    setMemberError("");
    setReading(!!value.departments.length);
    setPreview(value);
    setSelection(value.selection);
    setDepartment((current) =>
      value.departments.some((d) => d.id === current) ? current : (value.departments[0]?.id ?? ""),
    );
    setPage(1);
    setQuery("");
    setPlan(null);
  }, []);

  useEffect(() => {
    const current = ++request.current;
    let cancelled = false;
    if (!preview || !department) return;
    queryDirectoryMembers(preview.id, selection, department, query, page)
      .then((value) => {
        if (!cancelled && current === request.current) setMembers(value);
      })
      .catch((e: unknown) => {
        if (!cancelled && current === request.current) setMemberError(message(e));
      })
      .finally(() => {
        if (!cancelled && current === request.current) setReading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [preview, selection, department, query, page, retry]);

  function invalidate() {
    request.current++;
    setMembers(null);
    setMemberError("");
    setReading(true);
    setRetry((value) => value + 1);
  }
  async function start() {
    if (fetching.current) return;
    fetching.current = true;
    setBusy(true);
    setError("");
    try {
      const value = await previewDirectory();
      acceptPreview(value);
      setResult(null);
    } catch (e) {
      setError(message(e));
    } finally {
      fetching.current = false;
      setBusy(false);
    }
  }
  async function review() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      setPlan(await planDirectory(preview.id, selection));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!preview || !plan) return;
    setBusy(true);
    setError("");
    try {
      const value = await confirmDirectory(preview.id, plan.selection);
      setResult(value.run);
      setPlan(null);
      await onDone();
      // 保存完成只重读本地账号，不再次调用飞书；已提交预览退出选择模式。
      request.current++;
      setPreview(null);
      setMembers(null);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return {
    preview,
    selection,
    department,
    query,
    page,
    members,
    plan,
    result,
    busy,
    reading,
    error,
    memberError,
    closePreview: () => {
      request.current++;
      setPreview(null);
      setMembers(null);
      setPlan(null);
      setError("");
    },
    start,
    review,
    confirm,
    back: () => setPlan(null),
    cancel: () => {
      if (!preview) return;
      invalidate();
      setSelection(preview.selection);
      setPlan(null);
      setError("");
    },
    chooseDepartment: (id: string) => {
      if (preview) invalidate();
      setDepartment(id);
      setPage(1);
      setQuery("");
    },
    search: (value: string) => {
      invalidate();
      setQuery(value);
      setPage(1);
    },
    changePage: (value: number) => {
      invalidate();
      setPage(value);
    },
    retryMembers: () => {
      invalidate();
    },
    changeSelection: (value: DirectorySelection) => {
      invalidate();
      setSelection(value);
      setPlan(null);
    },
  };
}
