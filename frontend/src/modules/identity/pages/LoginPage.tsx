import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { Button } from "../../../shared/components/Button";
import { paths } from "../../../app/paths";
import { getLoginDestination } from "../login-navigation";
import { useSession } from "../session-context";
import "./login.css";

export function LoginPage() {
  const { phase, busy, error, retry, signIn } = useSession();
  const location = useLocation();
  const state: unknown = location.state;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const usernameInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const feedback = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!error || busy) return;
    if (phase === "error") feedback.current?.focus();
    else if (phase === "login") {
      // 失败后回到需要填写的位置，避免禁用控件后丢失键盘焦点。
      if (usernameInput.current?.value) passwordInput.current?.focus();
      else usernameInput.current?.focus();
    }
  }, [error, busy, phase]);

  if (location.search || location.hash) {
    return <Navigate to={paths.login} state={state} replace />;
  }
  if (phase === "ready") return <Navigate to={getLoginDestination(state)} replace />;

  return (
    <main className="identity-access">
      <div className="identity-access__content">
        <div className="identity-access__brand">
          <span className="identity-access__mark" aria-hidden="true">
            N
          </span>
          <strong>发票对账平台</strong>
        </div>
        <section
          className="identity-login"
          aria-busy={busy || phase === "loading"}
          aria-labelledby="identity-title"
        >
          <header className="identity-login__heading">
            <h1 id="identity-title">登录工作台</h1>
            <p>使用工作台账号和密码，进入财务工作台。</p>
          </header>
          {error && (
            <p
              id="identity-feedback"
              className="identity-login__feedback"
              ref={feedback}
              tabIndex={-1}
              role="alert"
            >
              {error}
            </p>
          )}
          {phase === "loading" ? (
            <div className="identity-login__state" role="status">
              <span className="identity-login__spinner" aria-hidden="true" />
              <strong>正在检查登录状态…</strong>
              <p>正在确认当前会话，请稍候。</p>
            </div>
          ) : phase === "error" ? (
            <div className="identity-login__state">
              <p>暂时无法确认登录状态，请检查连接后重试。</p>
              <Button onClick={retry}>重新检查会话</Button>
            </div>
          ) : (
            <form
              className="identity-login__form"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                if (busy) return;
                const submitted = password;
                setPassword("");
                setPasswordVisible(false);
                void signIn(username, submitted);
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
          )}
          <p className="identity-login__help">账号或密码有疑问，请联系系统管理员。</p>
        </section>
        <p className="identity-access__note">工作台账号与 NetSuite、柠檬云账号独立。</p>
      </div>
    </main>
  );
}
