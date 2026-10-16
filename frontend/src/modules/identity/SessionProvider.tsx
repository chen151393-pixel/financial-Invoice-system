import type { ReactNode } from "react";
import { SessionContext } from "./session-context";
import { useSessionState } from "./hooks/useSessionState";

/** 登录页与受保护页面共享同一份会话状态。 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const session = useSessionState();
  return <SessionContext value={session}>{children}</SessionContext>;
}
