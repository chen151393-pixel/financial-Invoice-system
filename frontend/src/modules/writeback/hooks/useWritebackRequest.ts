import { useEffect, useRef, useState } from "react";
import { executeWriteback, getWritebackRequest, isNotConnected, verifyWriteback } from "../api";
import type { WritebackRequest } from "../types";

type Action = "" | "execute" | "verify";

/**
 * 读取一次回写请求；执行中按后端 poll 标记轮询。执行和核实只提交一次，
 * 响应丢失时不自动重发，页面刷新后以后端记录为准。
 */
export function useWritebackRequest(requestId: string) {
  const [data, setData] = useState<WritebackRequest | null>(null);
  const [error, setError] = useState("");
  const [notConnected, setNotConnected] = useState(false);
  const [action, setAction] = useState<Action>("");
  const [attempt, setAttempt] = useState(0);
  const liveId = useRef(requestId);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    liveId.current = requestId;
    async function load() {
      try {
        const value = await getWritebackRequest(requestId);
        if (!active) return;
        setData(value);
        setError("");
        setNotConnected(false);
        if (value.poll) timer = setTimeout(() => void load(), 3000);
      } catch (failure) {
        if (!active) return;
        if (isNotConnected(failure)) setNotConnected(true);
        else setError(failure instanceof Error ? failure.message : "读取回写记录失败");
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [requestId, attempt]);

  async function run(kind: Exclude<Action, "">, call: (id: string) => Promise<WritebackRequest>) {
    const id = requestId;
    setAction(kind);
    setError("");
    try {
      const value = await call(id);
      if (liveId.current === id) setData(value);
      return true;
    } catch (failure) {
      if (liveId.current !== id) return false;
      setError(
        isNotConnected(failure)
          ? "回写执行接口尚未接入，未向 NS 提交任何内容"
          : failure instanceof Error
            ? `${failure.message}。请刷新查看记录状态，不要重复提交`
            : "提交结果未知，请刷新查看记录状态，不要重复提交",
      );
      return false;
    } finally {
      if (liveId.current === id) setAction("");
    }
  }

  return {
    data: data?.requestId === requestId ? data : null,
    error,
    notConnected,
    action,
    refresh: () => setAttempt((value) => value + 1),
    execute: () => run("execute", executeWriteback),
    verify: () => run("verify", verifyWriteback),
  };
}
