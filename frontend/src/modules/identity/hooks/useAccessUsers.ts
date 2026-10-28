import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { queryAccessUsers, saveDepartmentRoles, saveUserAccess } from "../api";
import type { UserList } from "../types";

export function useAccessUsers(onSaved: () => Promise<void>, fixedDepartment?: number | null) {
  const [params, setParams] = useSearchParams();
  const query = params.get("member") ?? "";
  const department =
    fixedDepartment === undefined
      ? (params.get("department") ?? "")
      : fixedDepartment === null
        ? ""
        : String(fixedDepartment);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [data, setData] = useState<UserList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const request = useRef(0);
  const reload = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError("");
    try {
      const result = await queryAccessUsers(query, department, page);
      if (current === request.current) setData(result);
    } catch (e) {
      if (current === request.current) setError(e instanceof Error ? e.message : "人员读取失败");
    } finally {
      if (current === request.current) setLoading(false);
    }
  }, [query, department, page]);
  useEffect(() => {
    const current = ++request.current;
    let cancelled = false;
    queryAccessUsers(query, department, page)
      .then((result) => {
        if (!cancelled && current === request.current) setData(result);
      })
      .catch((e: unknown) => {
        if (!cancelled && current === request.current)
          setError(e instanceof Error ? e.message : "人员读取失败");
      })
      .finally(() => {
        if (!cancelled && current === request.current) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, department, page]);
  function filter(value: string, dept: string, nextPage = 1) {
    const targetDepartment = fixedDepartment === undefined ? dept : department;
    if (value === query && targetDepartment === department && nextPage === page) {
      void reload();
      return;
    }
    request.current++;
    setLoading(true);
    setError("");
    setParams(
      {
        ...(value ? { member: value } : {}),
        ...(targetDepartment ? { department: targetDepartment } : {}),
        ...(nextPage > 1 ? { page: String(nextPage) } : {}),
      },
      { replace: true },
    );
  }
  return {
    data,
    error,
    loading,
    query,
    department,
    page,
    filter,
    reload,
    saveUser: async (id: number, roles: string[], custom: boolean, enabled: boolean) => {
      await saveUserAccess(id, roles, custom, enabled);
      await reload();
      await onSaved();
    },
    saveDepartment: async (id: number, roles: string[]) => {
      await saveDepartmentRoles(id, roles);
      await reload();
      await onSaved();
    },
  };
}
