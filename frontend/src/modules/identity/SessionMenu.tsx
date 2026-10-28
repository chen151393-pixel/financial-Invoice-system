import { Button } from "../../shared/components/ui";
import { useSession } from "./session-context";
import "./session-access.css";

/** 侧栏底部：当前登录人姓名、角色与退出；姓名和角色来自后端会话。 */
export function SessionMenu() {
  const { signOut, busy, error, user } = useSession();
  return (
    <div className="identity-session-menu">
      {user && (
        <div className="identity-session-menu__user">
          <span className="identity-session-menu__avatar" aria-hidden="true">
            {user.name.slice(0, 1)}
          </span>
          <span className="identity-session-menu__text">
            <strong>{user.name}</strong>
            <span>{user.roles.map((role) => role.label).join("、") || "未分配角色"}</span>
          </span>
        </div>
      )}
      {error && <span role="alert">{error}</span>}
      <Button disabled={busy} onClick={() => void signOut()}>
        {busy ? "正在退出…" : "退出登录"}
      </Button>
    </div>
  );
}
