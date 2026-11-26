import { useEffect, useEffectEvent, useRef, useState } from "react";
import { queryCustomsImports } from "./customs-api";
import type { CustomsImportJob } from "./customs-types";

/** 持续读取服务器作业；上传被接受与真正完成是两个不同状态。 */
export function useCustomsImports(onCompleted: () => void) {
  const [jobs, setJobs] = useState<CustomsImportJob[]>([]);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const known = useRef(new Map<string, CustomsImportJob["status"]>());
  const completed = useEffectEvent(onCompleted);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const { items } = await queryCustomsImports(controller.signal);
        if (controller.signal.aborted) return;
        const finished = items.some(
          (job) => job.status === "completed" && known.current.get(job.id) !== "completed",
        );
        items.forEach((job) => known.current.set(job.id, job.status));
        setJobs(items);
        setError("");
        if (finished) completed();
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(error instanceof Error ? error.message : "导入进度读取失败，请刷新核实");
      }
      if (!controller.signal.aborted) timer = setTimeout(() => void load(), 2000);
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [refresh]);

  function queued(job: CustomsImportJob) {
    known.current.set(job.id, job.status);
    setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    setRefresh((value) => value + 1);
  }
  return { jobs, error, queued };
}
