import { useEffect, useRef, useState } from "react";
import {
  createProgress,
  getProgress,
  pullRecords,
  type DateRange,
  type PullResult,
  type SourceKind,
  type SyncProgress,
} from "./api";
import { pollProgress } from "./progress-poll";
import { pullDateRange } from "./range-pull";

type Status = "idle" | "running" | "stopping" | "completed" | "partial" | "stopped" | "failed";

export function useRangePull(kind: SourceKind, onBusyChange: (busy: boolean) => void) {
  const [pages, setPages] = useState<PullResult[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<SyncProgress | null>(null);
  const [progressUnavailable, setProgressUnavailable] = useState(false);
  const [submittedRange, setSubmittedRange] = useState<DateRange | null>(null);
  const current = useRef(0);
  const stopRequested = useRef(false);
  const running = useRef(false);
  useEffect(
    () => () => {
      current.current += 1;
    },
    [],
  );

  async function start(range: DateRange, save: boolean) {
    if (running.current) return;
    running.current = true;
    const id = ++current.current;
    stopRequested.current = false;
    setPages([]);
    setPageIndex(0);
    setSubmittedRange({ ...range });
    setStatus("running");
    setError("");
    setProgress(null);
    setProgressUnavailable(false);
    onBusyChange(true);
    try {
      let received = 0;
      const outcome = await pullDateRange({
        range,
        save,
        readPage: async (offset, dates, persist) => {
          if (!persist) return pullRecords(kind, offset, dates);
          setProgress(null);
          setProgressUnavailable(false);
          let progressId: string | undefined;
          try {
            ({ progressId } = await createProgress());
          } catch {
            if (id === current.current) setProgressUnavailable(true);
          }
          // 只申请了进度而尚未提交时离开页面，不再发起保存。
          if (id !== current.current) throw new Error("页面已离开，未发起本批保存");
          if (!progressId) return pullRecords(kind, offset, dates, true);
          const dispose = pollProgress({
            read: () => getProgress(progressId),
            onProgress: (value) => {
              setProgress(value);
              setProgressUnavailable(false);
            },
            onUnavailable: () => setProgressUnavailable(true),
            isCurrent: () => id === current.current,
          });
          try {
            return await pullRecords(kind, offset, dates, true, progressId);
          } finally {
            dispose();
          }
        },
        shouldStop: () => stopRequested.current || id !== current.current,
        onPage: (page) => {
          if (id !== current.current) return;
          setPages((previous) => [...previous, page]);
          setPageIndex(received++);
        },
      });
      if (id === current.current) setStatus(outcome);
    } catch (error) {
      if (id === current.current) {
        setError(error instanceof Error ? error.message : "拉取失败");
        setStatus("failed");
      }
    } finally {
      running.current = false;
      if (id === current.current) onBusyChange(false);
    }
  }

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
    progress,
    progressUnavailable,
    start,
    stop,
    busy: status === "running" || status === "stopping",
  };
}
