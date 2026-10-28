import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/ui";

/** 应急管理员账号密码表单；校验与失败次数限制都在后端。 */
export function PasswordLoginForm({
  busy,
  error,
  onSubmit,
}: {
  busy: boolean;
  error: string;
  onSubmit: (username: string, password: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const usernameInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!error || busy) return;
    // 失败后回到需要填写的位置，避免禁用控件后丢失键盘焦点。
    if (usernameInput.current?.value) passwordInput.current?.focus();
    else usernameInput.current?.focus();
  }, [error, busy]);

  return (
    <form
      className="identity-login__form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (busy) return;
        const submitted = password;
        setPassword("");
        setPasswordVisible(false);
        onSubmit(username, submitted);
      }}
    >
      <div className="identity-login__field">
        <label htmlFor="identity-username">用户名</label>
        <input
          id="identity-username"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="请输入用户名"
          ref={usernameInput}
          value={username}
          disabled={busy}
          aria-describedby={error ? "identity-feedback" : undefined}
          onChange={(event) => setUsername(event.target.value)}
        />
      </div>
      <div className="identity-login__field">
        <label htmlFor="identity-password">密码</label>
        <div className="identity-login__password">
          <input
            id="identity-password"
            type={passwordVisible ? "text" : "password"}
            name="password"
            autoComplete="current-password"
            placeholder="请输入密码"
            ref={passwordInput}
            value={password}
            disabled={busy}
            aria-describedby={error ? "identity-feedback" : undefined}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button
            className="identity-login__visibility"
            aria-label={passwordVisible ? "隐藏密码" : "显示密码"}
            aria-controls="identity-password"
            aria-pressed={passwordVisible}
            disabled={busy}
            onClick={() => setPasswordVisible((value) => !value)}
          >
            {passwordVisible ? "隐藏" : "显示"}
          </Button>
        </div>
      </div>
      <Button className="identity-login__submit" type="submit" variant="primary" disabled={busy}>
        {busy ? "正在登录…" : "登录工作台"}
      </Button>
    </form>
  );
}
