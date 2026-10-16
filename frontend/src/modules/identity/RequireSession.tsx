import { Navigate, Outlet, useLocation } from "react-router";
import { paths } from "../../app/paths";
import { useSession } from "./session-context";

/** 守卫只负责跳转，登录表单由 /login 独立页面渲染。 */
export function RequireSession() {
  const { phase } = useSession();
  const { pathname, search, hash } = useLocation();
  if (phase !== "ready") {
    return <Navigate to={paths.login} state={{ from: pathname + search + hash }} replace />;
  }
  return <Outlet />;
}
