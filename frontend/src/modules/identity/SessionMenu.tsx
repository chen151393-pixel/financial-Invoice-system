import { Button } from "../../shared/components/Button";
import { useSession } from "./session-context";
import "./session-access.css";

export function SessionMenu() {
  const { signOut, busy, error } = useSession();
  return (
    <div className="identity-session-menu">
      {error && <span role="alert">{error}</span>}
      <Button disabled={busy} onClick={() => void signOut()}>
        {busy ? "正在退出…" : "退出登录"}
      </Button>
    </div>
  );
}
