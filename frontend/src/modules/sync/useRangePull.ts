import { useEffect, useRef, useState } from "react";
import { pullRecords, type DateRange, type PullResult, type SourceKind } from "./api";
import { pullDateRange } from "./range-pull";

type Status = "idle" | "running" | "stopping" | "completed" | "stopped" | "failed";

export function useRangePull(kind: SourceKind, onBusyChange: (busy: boolean) => void) {
  const [pages, setPages] = useState<PullResult[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
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
    onBusyChange(true);
    try {
      let received = 0;
      const outcome = await pullDateRange({
        range,
        save,
        readPage: (offset, dates, persist) => pullRecords(kind, offset, dates, persist),
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
    start,
    stop,
    busy: status === "running" || status === "stopping",
  };
}
