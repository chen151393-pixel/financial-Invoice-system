import { useCallback, useEffect, useRef, useState } from "react";
import { getRolePages, saveRolePages } from "../api";
import type { RolePageOverview, RolePages } from "../types";

export function useRolePages() {
  const [data, setData] = useState<RolePageOverview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [generation, setGeneration] = useState(0);
  const request = useRef(0);
  const reload = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError("");
    try {
      const value = await getRolePages();
      if (current === request.current) {
        setData(value);
        setGeneration((n) => n + 1);
      }
    } catch (failure) {
      if (current === request.current)
        setError(failure instanceof Error ? failure.message : "角色权限读取失败");
    } finally {
      if (current === request.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    const current = ++request.current;
    getRolePages()
      .then((value) => {
        if (current === request.current) setData(value);
      })
      .catch((failure: unknown) => {
        if (current === request.current)
          setError(failure instanceof Error ? failure.message : "角色权限读取失败");
      })
      .finally(() => {
        if (current === request.current) setLoading(false);
      });
    return () => {
      request.current += 1;
    };
  }, []);
  async function save(role: RolePages, pages: string[]) {
    const saved = await saveRolePages(role.code, pages, role.revision);
    setData(
      (current) =>
        current && {
          ...current,
          roles: current.roles.map((item) => (item.code === saved.code ? saved : item)),
        },
    );
    return saved;
  }
  return { data, error, loading, reload, save, generation };
}
