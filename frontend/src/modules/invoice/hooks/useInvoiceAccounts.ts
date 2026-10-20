import { useEffect, useState } from "react";
import { getInvoiceAccounts } from "../api/invoice";
import type { InvoiceAccountOption } from "../types/invoice";

export function useInvoiceAccounts(version: number) {
  const [state, setState] = useState({ items: [] as InvoiceAccountOption[], loading: true, error: "" });
  useEffect(() => {
    let active = true;
    getInvoiceAccounts().then(
      ({ items }) => {
        if (active) setState({ items, loading: false, error: "" });
      },
      (reason: unknown) => {
        if (active)
          setState((current) => ({
            ...current,
            loading: false,
            error: reason instanceof Error ? reason.message : "账套选项读取失败",
          }));
      },
    );
    return () => {
      active = false;
    };
  }, [version]);
  return state;
}
