import { useEffect, useRef, useState } from "react";
import {
  getRun,
  pullRecords,
  startRun,
  type DateRange,
  type NsRun,
  type PullResult,
  type SaveKind,
  type SourceKind,
} from "./api";
import { pullDateRange } from "./range-pull";
import { waitForRun } from "./run-wait";

type Status = "idle" | "running" | "stopping" | "completed" | "partial" | "stopped" | "recovered" | "failed";

// 未确认结束的批次编号保存在本标签页，刷新后按编号恢复查看，不重新提交。
const pendingKey = (kind: SourceKind) => `ns-sync-run:${kind}`;

function readPending(kind: SourceKind) {
  try {
    return sessionStorage.getItem(pendingKey(kind)) ?? "";
  } catch {
    return "";
  }
}

function writePending(kind: SourceKind, requestId: string) {
  try {
    if (requestId) sessionStorage.setItem(pendingKey(kind), requestId);
    else sessionStorage.removeItem(pendingKey(kind));
  } catch {
    /* 浏览器禁用存储时只是无法在刷新后恢复，不影响本次查询。 */
  }
}

export function useRangePull(kind: SourceKind, onBusyChange: (busy: boolean) => void) {
  // 刷新前未确认结束的批次：首屏即进入查询状态，按原编号恢复查看。
  const [recovering] = useState(() => readPending(kind));
  const [pages, setPages] = useState<PullResult[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [status, setStatus] = useState<Status>(() => (recovering ? "running" : "idle"));
  const [error, setError] = useState("");
  const [run, setRun] = useState<NsRun | null>(null);
  const [progressUnavailable, setProgressUnavailable] = useState(false);
  const [submittedRange, setSubmittedRange] = useState<DateRange | null>(null);
  const current = useRef(0);
  const stopRequested = useRef(false);
  const running = useRef(false);

  function begin() {
    running.current = true;
    const id = ++current.current;
    stopRequested.current = false;
    setPages([]);
    setPageIndex(0);
    setStatus("running");
    setError("");
    setRun(null);
    setProgressUnavailable(false);
    onBusyChange(true);
    return id;
  }

  function finish(id: number) {
    // 已被卸载或替换的旧流程不改动当前流程的占用状态。
    if (id !== current.current) return;
    running.current = false;
    onBusyChange(false);
  }

  function waitBatch(id: number, requestId: string, submit: () => Promise<NsRun>) {
    return waitForRun({
      submit,
      read: () => getRun(requestId),
      onRun: (value) => {
        if (id !== current.current) return;
        setRun(value);
        setProgressUnavailable(false);
      },
      onUnavailable: () => {
        if (id === current.current) setProgressUnavailable(true);
      },
      isCurrent: () => id === current.current,
    }).then(
      (page) => {
        writePending(kind, "");
        return page;
      },
      (cause: unknown) => {
        // 只有后端给出结束状态或明确未创建时才清除；离开页面等情况保留编号供恢复。
        const message = cause instanceof Error ? cause.message : "";
        if (id === current.current && !message.startsWith("已离开")) writePending(kind, "");
        throw cause;
      },
    );
  }

  async function start(range: DateRange, save: boolean) {
    if (running.current) return;
    const id = begin();
    setSubmittedRange({ ...range });
    try {
      let received = 0;
      const outcome = await pullDateRange({
        range,
        save,
        readPage: (offset, dates, persist) => {
          if (!persist) return pullRecords(kind, offset, dates);
          if (kind === "purchase-orders") throw new Error("标准采购订单尚未配置独立存储，不能保存");
          const saveKind: SaveKind = kind;
          const requestId = crypto.randomUUID();
          writePending(kind, requestId);
          setRun(null);
          setProgressUnavailable(false);
          return waitBatch(id, requestId, () => startRun(saveKind, requestId, offset, dates));
        },
        shouldStop: () => stopRequested.current || id !== current.current,
        onPage: (page) => {
          if (id !== current.current) return;
          setPages((previous) => [...previous, page]);
          setPageIndex(received++);
        },
      });
      if (id === current.current) setStatus(outcome);
    } catch (cause) {
      if (id === current.current) {
        setError(cause instanceof Error ? cause.message : "拉取失败");
        setStatus("failed");
      }
    } finally {
      finish(id);
    }
  }

  useEffect(() => {
    // 卸载时使在途流程失效，停止轮询并忽略迟到响应。
    const cleanup = () => {
      current.current += 1;
      running.current = false;
    };
    if (!recovering) return cleanup;
    running.current = true;
    const id = ++current.current;
    onBusyChange(true);
    waitBatch(id, recovering, () => getRun(recovering))
      .then(
        (page) => {
          if (id !== current.current) return;
          setPages([page]);
          setStatus("recovered");
        },
        (cause: unknown) => {
          if (id !== current.current) return;
          setError(cause instanceof Error ? cause.message : "上次批次结果查询失败");
          setStatus("failed");
        },
      )
      .finally(() => finish(id));
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅挂载时按原编号恢复一次；回调每次渲染重建，加入依赖会重复恢复。
  }, []);

  function stop() {
    stopRequested.current = true;
    setStatus("stopping");
  }

  return {
    pages,
    pageIndex,
    setPageIndex,
    status,
    error,
    submittedRange,
    run,
    progressUnavailable,
    start,
    stop,
    busy: status === "running" || status === "stopping",
  };
}
