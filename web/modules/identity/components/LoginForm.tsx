import { useState } from "react";
import { Button } from "../../../shared/components/Button";

export function LoginForm({
  busy,
  onLogin,
}: {
  busy: boolean;
  onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  return (
    <form
      className="ui-panel live-login"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const submittedPassword = password;
        setPassword("");
        void onLogin(username, submittedPassword);
      }}
    >
      <h2>登录业务后端</h2>
      <label>
        用户名
        <input
          autoComplete="username"
          value={username}
          disabled={busy}
          onChange={(event) => setUsername(event.target.value)}
        />
      </label>
      <label>
        密码
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          disabled={busy}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <Button type="submit" variant="primary" disabled={busy}>
        登录
      </Button>
      <p>使用服务器配置的后台账号。</p>
    </form>
  );
}
