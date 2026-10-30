import { HttpError } from "../../shared/api/http";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  lemonConfiguration,
  queryLemonAccounts,
  selectLemonAccount,
  pullLemonInvoices,
} from "./lemon-invoice-api";
import type { LemonConfiguration, LemonPullRequest } from "./lemon-invoice-api";
import type { LemonAccountOption } from "./types/background";

const EMPTY_TYPES: string[] = [];

export function useLemonInvoices() {
  const [data, setData] = useState<LemonConfiguration | null>(null);
  const [accounts, setAccounts] = useState<LemonAccountOption[] | null>(null);
  const [asid, setAsid] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedTypes, setBusinessTypes] = useState<string[] | null>(null);
  const businessTypes = selectedTypes ?? data?.defaultBusinessTypes ?? EMPTY_TYPES;
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const running = useRef(false);
  const pending = useRef<LemonPullRequest | null>(null);

  const run = useCallback(
    async (action: "refresh" | "query" | "select" | "pull") => {
      if (running.current) return;
      running.current = true;
      const current = ++sequence.current;
      setBusy(action);
      setError("");
      const active = () => current === sequence.current;
      try {
        if (action === "query") {
          const response = await queryLemonAccounts();
          if (active()) {
            setAccounts(response.items);
            setAsid("");
          }
        } else if (action === "select") {
          const response = await selectLemonAccount(asid);
          if (active()) setData(response);
        } else if (action === "pull") {
          // 同一未获响应的提交保留请求编号，绝不自动重复发起保存。
          const body = pending.current ?? {
            asid: data?.selected?.asid ?? "",
            startDate,
            endDate,
            businessTypes: [...businessTypes],
            requestId: crypto.randomUUID(),
          };
          pending.current = body;
          const result = await pullLemonInvoices(body);
          if (result.status !== "running") pending.current = null;
          if (active()) setData((previous) => (previous ? { ...previous, latest: result } : previous));
        }
        const config = await lemonConfiguration();
        if (active()) {
          setData(config);
          if (config.latest?.requestId === pending.current?.requestId && config.latest?.status !== "running")
            pending.current = null;
        }
      } catch (cause) {
        if (cause instanceof HttpError && cause.status < 500) pending.current = null;
        if (active()) {
          setError(cause instanceof Error ? cause.message : "操作失败，请刷新同步状态");
          // 写入响应丢失后只查询状态，不重放保存请求。
          try {
            const config = await lemonConfiguration();
            if (active()) {
              setData(config);
              if (
                config.latest?.requestId === pending.current?.requestId &&
                config.latest?.status !== "running"
              )
                pending.current = null;
            }
          } catch {
            if (active()) setData(null);
          }
        }
      } finally {
        running.current = false;
        if (active()) setBusy("");
      }
    },
    [asid, data, startDate, endDate, businessTypes],
  );

  useEffect(() => {
    const current = ++sequence.current;
    void lemonConfiguration()
      .then((response) => {
        if (current === sequence.current) setData(response);
      })
      .catch((cause: unknown) => {
        if (current === sequence.current)
          setError(cause instanceof Error ? cause.message : "读取同步状态失败");
      });
    return () => {
      sequence.current += 1;
    };
  }, []);
  return {
    data,
    accounts,
    asid,
    setAsid,
    startDate,
    setStartDate,
    endDate,
    setEndDate,
    businessTypes,
    setBusinessTypes,
    busy,
    error,
    run,
  };
}
