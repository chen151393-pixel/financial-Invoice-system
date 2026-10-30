import { useCallback, useEffect, useRef, useState } from "react";
import { getNsPlan, saveNsPlan } from "../api/ns-plan-api";
import type { NsPlan, NsPlanConfig } from "../types/ns-plan";

/** NS 定时计划的读取与保存；过期响应不覆盖新状态，失败不自动重试。 */
export function useNsPlan() {
  const [data, setData] = useState<NsPlanConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const mounted = useRef(false);
  const perform = useCallback(
    async (action: () => Promise<NsPlanConfig>, done?: (value: NsPlanConfig) => void) => {
      const current = ++generation.current;
      setBusy(true);
      setError("");
      setMessage("");
      try {
        const value = await action();
        if (mounted.current && current === generation.current) {
          setData(value);
          done?.(value);
        }
      } catch (error) {
        if (mounted.current && current === generation.current)
          setError(error instanceof Error ? error.message : "操作失败，请刷新后查看计划实际状态");
      } finally {
        if (mounted.current && current === generation.current) setBusy(false);
      }
    },
    [],
  );
  useEffect(() => {
    mounted.current = true;
    const current = ++generation.current;
    void getNsPlan()
      .then((value) => {
        if (mounted.current && current === generation.current) setData(value);
      })
      .catch((error: unknown) => {
        if (mounted.current && current === generation.current)
          setError(error instanceof Error ? error.message : "读取同步计划失败");
      });
    return () => {
      mounted.current = false;
    };
  }, []);
  return {
    data,
    busy,
    error,
    message,
    refresh: () => perform(getNsPlan),
    save: (plan: NsPlan) =>
      perform(
        () => saveNsPlan(plan),
        (value) =>
          setMessage(
            value.plan.enabled
              ? "定时计划已保存并启用，已提交的批次继续使用原条件。"
              : "计划已暂停，已提交的批次继续执行。",
          ),
      ),
  };
}
