import { useCallback, useEffect, useRef, useState } from "react";
import { getAccess } from "../api";
import type { AccessOverview } from "../types";

const message = (failure: unknown) => (failure instanceof Error ? failure.message : "人员与权限读取失败");

/** 人员与权限总览；保存后重新读取，页面不自行推算生效角色。 */
export function useAccess() {
  const [data, setData] = useState<AccessOverview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const request = useRef(0);

  useEffect(() => {
    const current = ++request.current;
    getAccess()
      .then((value) => {
        if (current === request.current) setData(value);
      })
      .catch((failure: unknown) => {
        if (current === request.current) setError(message(failure));
      })
      .finally(() => {
        if (current === request.current) setLoading(false);
      });
  }, []);

  // 保存或同步后重新读取；较早发出的请求结果被忽略，避免旧数据覆盖新数据
  const reload = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError("");
    try {
      const value = await getAccess();
      if (current === request.current) setData(value);
    } catch (failure) {
      if (current === request.current) setError(message(failure));
    } finally {
      if (current === request.current) setLoading(false);
    }
  }, []);

  return { data, error, loading, reload };
}
