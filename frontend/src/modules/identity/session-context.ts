import { createContext, useContext } from "react";
import type { SessionUser } from "./types";

export type SessionPhase = "loading" | "login" | "ready" | "error";

export interface SessionState {
  phase: SessionPhase;
  /** 当前登录人；姓名、角色由后端返回 */
  user: SessionUser | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
  busy: boolean;
  error: string;
}

export const SessionContext = createContext<SessionState | null>(null);

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("会话入口尚未装配");
  return session;
}
