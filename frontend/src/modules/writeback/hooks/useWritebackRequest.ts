import { useEffect, useRef, useState } from "react";
import { getTask } from "../api";
import type { TaskDetail } from "../types";

/** 回写详情状态：同步提交锁、执行中只读轮询，以及响应丢失后的状态核实。 */
export function useWritebackRequest(requestId: string) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [writing, setWriting] = useState(false);
  const [unverified, setUnverified] = useState(false);
  // ref 同步加锁，阻止同一帧的快速重复点击；版本号阻止旧读取覆盖新操作结果。
  const inFlight = useRef(false);
  const readVersion = useRef(0);
  const currentId = useRef<string | null>(requestId);
  useEffect(() => {
    currentId.current = requestId;
    return () => {
      currentId.current = null;
    };
  }, [requestId]);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    const version = ++readVersion.current;
    getTask(requestId)
      .then((data) => {
        if (active && version === readVersion.current && !inFlight.current) {
          setTask(data);
          setError("");
          setUnverified(false);
        }
      })
      .catch((e: unknown) => {
        if (active && version === readVersion.current)
          setError(e instanceof Error ? e.message : "任务加载失败");
      });
    return () => {
      active = false;
    };
  }, [requestId, reload]);
  useEffect(() => {
    if (task?.state !== "executing" || busy || unverified) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const version = readVersion.current;
    async function poll() {
      try {
        const latest = await getTask(requestId);
        if (active && version === readVersion.current && !inFlight.current) {
          setTask(latest);
          setError("");
        }
      } catch {
        if (active) setError("正在回写，暂时无法读取最新状态；请等待或刷新任务状态核对，不要重复提交。");
      } finally {
        if (active) timer = setTimeout(() => void poll(), 2000);
      }
    }
    timer = setTimeout(() => void poll(), 2000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [requestId, task?.state, busy, unverified, reload]);
  async function run(operation: () => Promise<TaskDetail>, execute = false) {
    if (inFlight.current || unverified) return;
    inFlight.current = true;
    ++readVersion.current;
    const id = requestId;
    setBusy(true);
    setWriting(execute);
    setError("");
    try {
      const latest = await operation();
      if (currentId.current === id) setTask(latest);
    } catch (e) {
      if (currentId.current !== id) return;
      setError(e instanceof Error ? e.message : "操作失败，请刷新后核对");
      if (execute) {
        setUnverified(true);
        // POST 的返回丢失时只读核实，不重放写入，也不恢复旧页面上的可执行按钮。
        try {
          const latest = await getTask(id);
          if (currentId.current === id) {
            setTask(latest);
            setUnverified(false);
          }
        } catch {
          if (currentId.current === id)
            setError("回写请求未取得可核对的结果，请刷新任务状态核实；核实前不能再次回写。");
        }
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
      setWriting(false);
    }
  }
  return { task, error, busy, writing, unverified, run, refresh: () => setReload((value) => value + 1) };
}
