import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { querySupplierProfiles } from "../api/supplier-group";
import type { SupplierProfileList, SupplierProfileQuery } from "../types/supplier-group";

export function useSupplierProfiles() {
  const [params, setParams] = useSearchParams();
  const [refresh, setRefresh] = useState(0);
  const [remote, setState] = useState<
    | { kind: "loading" }
    | { kind: "error"; message: string; queryKey: string }
    | { kind: "ready"; data: SupplierProfileList; queryKey: string }
  >({ kind: "loading" });
  const positive = (key: string, fallback: number) => {
    const value = Number(params.get(key));
    return Number.isSafeInteger(value) && value > 0 ? value : fallback;
  };
  const query: SupplierProfileQuery = {
    keyword: params.get("keyword") || "",
    status: (params.get("status") || "all") as SupplierProfileQuery["status"],
    page: positive("page", 1),
    pageSize: positive("pageSize", 20),
  };
  const key = JSON.stringify(query);
  useEffect(() => {
    let active = true;
    void querySupplierProfiles(JSON.parse(key) as SupplierProfileQuery).then(
      (data) => {
        if (active) setState({ kind: "ready", data, queryKey: key });
      },
      (error: unknown) => {
        if (active)
          setState({
            kind: "error",
            queryKey: key,
            message: error instanceof Error ? error.message : "供应商档案读取失败",
          });
      },
    );
    return () => {
      active = false;
    };
  }, [key, refresh]);
  function change(patch: Partial<SupplierProfileQuery>) {
    setState({ kind: "loading" });
    const next = { ...query, page: 1, ...patch };
    setParams(Object.fromEntries(Object.entries(next).map(([name, value]) => [name, String(value)])));
    setRefresh((value) => value + 1);
  }
  function reload() {
    setState({ kind: "loading" });
    setRefresh((value) => value + 1);
  }
  const state = remote.kind === "loading" || remote.queryKey === key ? remote : { kind: "loading" as const };
  return { query, state, change, reload };
}
