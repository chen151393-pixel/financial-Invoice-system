import { useCallback, useEffect, useRef, useState } from "react";
import { getBackgroundConfig, querySyncAccounts, saveSyncPlan, submitSyncBatch } from "../api/background-api";
import type { BackgroundConfig, BatchInput, LemonAccountOption, Plan } from "../types/background";

export function useBackgroundConfig() {
  const [data, setData] = useState<BackgroundConfig | null>(null);
  const [accounts, setAccounts] = useState<LemonAccountOption[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const mounted = useRef(false);
  const perform = useCallback(
    async <T>(name: string, action: () => Promise<T>, accept: (value: T) => void) => {
      const current = ++generation.current;
      setBusy(name);
      setError("");
      setMessage("");
      try {
        const result = await action();
        if (mounted.current && current === generation.current) accept(result);
      } catch (error) {
        if (mounted.current && current === generation.current)
          setError(error instanceof Error ? error.message : "操作失败，请刷新查询原任务");
      } finally {
        if (mounted.current && current === generation.current) setBusy("");
      }
    },
    [],
  );
  const refresh = useCallback(() => perform("load", getBackgroundConfig, setData), [perform]);
  useEffect(() => {
    mounted.current = true;
    const current = ++generation.current;
    void getBackgroundConfig()
      .then((value) => {
        if (mounted.current && current === generation.current) setData(value);
      })
      .catch((error: unknown) => {
        if (mounted.current && current === generation.current)
          setError(error instanceof Error ? error.message : "读取配置失败");
      });
    return () => {
      mounted.current = false;
    };
  }, []);
  return {
    data,
    accounts,
    busy,
    error,
    message,
    refresh,
    query: () => perform("accounts", querySyncAccounts, (value) => setAccounts(value.items)),
    save: (plan: Plan) =>
      perform(
        "save",
        () => saveSyncPlan(plan),
        (value) => {
          setData(value);
          setMessage(
            value.plan.enabled
              ? "定时计划已启用，已运行任务继续使用原条件。"
              : "计划已暂停，已提交任务继续执行。",
          );
        },
      ),
    submit: (body: BatchInput, accept: (id: string) => void) =>
      perform(
        "submit",
        () => submitSyncBatch(body),
        (batch) => accept(batch.requestId),
      ),
  };
}
