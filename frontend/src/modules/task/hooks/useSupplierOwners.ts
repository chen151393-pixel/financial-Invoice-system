import { useEffect, useState } from "react";
import { getOwnerOptions, queryOwners } from "../api/supplier-owner";
import type { OwnerList, OwnerOptions, OwnerQuery } from "../types/supplier-owner";

export const initialOwnerQuery: OwnerQuery = {
  supplierName: "",
  companyId: null,
  memberId: null,
  status: "all",
  page: 1,
  pageSize: 20,
};
type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: OwnerList; options: OwnerOptions };

export function useSupplierOwners() {
  const [query, setQuery] = useState(initialOwnerQuery);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void Promise.all([queryOwners(query, controller.signal), getOwnerOptions(controller.signal)])
      .then(([data, options]) => {
        if (active) setState({ kind: "ready", data, options });
      })
      .catch((error: unknown) => {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "人员关联读取失败" });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [query, refresh]);
  function search(next: OwnerQuery) {
    setState({ kind: "loading" });
    setQuery(next);
  }
  function reload() {
    setState({ kind: "loading" });
    setRefresh((value) => value + 1);
  }
  return { state, query, search, reload };
}
