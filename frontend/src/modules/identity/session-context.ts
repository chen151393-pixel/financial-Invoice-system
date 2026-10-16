import { createContext, useContext } from "react";

export type SessionPhase = "loading" | "login" | "ready" | "error";

export interface SessionState {
  phase: SessionPhase;
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
