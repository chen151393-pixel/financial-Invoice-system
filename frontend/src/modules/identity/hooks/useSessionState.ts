import { useEffect, useRef, useState } from "react";
import { HttpError, onUnauthorized } from "../../../shared/api/http";
import { getSession, login, logout } from "../api";
import type { SessionPhase, SessionState } from "../session-context";
import type { SessionUser } from "../types";

export function useSessionState(): SessionState {
  const [phase, setPhase] = useState<SessionPhase>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const submitting = useRef(false);

  useEffect(() => {
    let active = true;
    getSession()
      .then((session) => {
        if (!active) return;
        setUser(session.user ?? null);
        setPhase("ready");
      })
      .catch((failure: unknown) => {
        if (!active) return;
        if (failure instanceof HttpError && failure.status === 401) setPhase("login");
        else {
          setError(failure instanceof Error ? failure.message : "无法检查会话");
          setPhase("error");
        }
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  useEffect(() => {
    if (phase !== "ready") return;
    return onUnauthorized(() => {
      setError("登录已失效，请重新登录。");
      setPhase("login");
    });
  }, [phase]);

  async function signIn(username: string, password: string) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      const session = await getSession();
      setUser(session.user ?? null);
      setPhase("ready");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "登录失败");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function signOut() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await logout();
      setUser(null);
      setPhase("login");
    } catch (failure) {
      if (failure instanceof HttpError && failure.status === 401) setPhase("login");
      else setError(failure instanceof Error ? failure.message : "退出失败，请重试");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  function retry() {
    setPhase("loading");
    setError("");
    setAttempt((value) => value + 1);
  }

  return { phase, user, error, busy, signIn, signOut, retry };
}
