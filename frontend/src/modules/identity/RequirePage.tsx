import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { paths, type View } from "../../app/paths";
import { useSession } from "./session-context";

/** 只按后端页面列表跳转；详情与列表共用同一权限。 */
export function RequirePage({ view, children }: { view: View; children: ReactNode }) {
  const { user } = useSession();
  return user?.pages?.includes(view) ? children : <Navigate to={paths.forbidden} replace />;
}
