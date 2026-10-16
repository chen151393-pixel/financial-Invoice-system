import { useEffect, useRef, useState } from "react";
import {
  beginLemonBinding,
  confirmLemonBinding,
  getLemonBinding,
  verifyLemonBinding,
  type LemonBinding,
} from "./lemon-api";

export function useLemonBinding() {
  const [data, setData] = useState<LemonBinding | null>(null);
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const request = useRef(0);
  useEffect(() => {
    const id = ++request.current;
    getLemonBinding()
      .then((value) => {
        if (id === request.current) setData(value);
      })
      .catch((failure: unknown) => {
        if (id === request.current) setError(failure instanceof Error ? failure.message : "读取绑定状态失败");
      });
    return () => {
      request.current += 1;
    };
  }, [attempt]);

  async function run(action: "start" | "confirm" | "verify") {
    const id = ++request.current;
    setBusy(action);
    setError("");
    const submittedPassword = password;
    setPassword("");
    try {
      if (action === "start") {
        const result = await beginLemonBinding(mobile);
        if (id === request.current) window.location.assign(result.authorizationUrl);
      } else {
        const result =
          action === "confirm" ? await confirmLemonBinding(submittedPassword) : await verifyLemonBinding();
        if (id === request.current) setData(result);
      }
    } catch (failure) {
      if (id !== request.current) return;
      setError(failure instanceof Error ? failure.message : "处理失败，请核实绑定状态");
      // 写请求断开时先读取服务端状态，不用旧 allowed 继续提交。
      setData(null);
      try {
        const latest = await getLemonBinding();
        if (id === request.current) setData(latest);
      } catch {
        if (id === request.current) setError("无法核实最新绑定状态，请恢复连接后刷新状态，勿重复提交。");
      }
    } finally {
      if (id === request.current) setBusy("");
    }
  }

  function refresh() {
    request.current += 1;
    setError("");
    setPassword("");
    setData(null);
    setAttempt((value) => value + 1);
  }
  return { data, mobile, password, busy, error, setMobile, setPassword, run, refresh };
}
