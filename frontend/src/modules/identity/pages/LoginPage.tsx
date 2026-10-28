import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { Button } from "../../../shared/components/ui";
import { paths } from "../../../app/paths";
import { startFeishuLogin } from "../api";
import { PasswordLoginForm } from "../components/PasswordLoginForm";
import { useLoginOptions } from "../hooks/useLoginOptions";
import { getLoginDestination } from "../login-navigation";
import { useSession } from "../session-context";
import "./login.css";

export function LoginPage() {
  const { phase, busy, error, retry, signIn } = useSession();
  const location = useLocation();
  const state: unknown = location.state;
  const { options, failure, loadError } = useLoginOptions(phase === "login");
  const [redirecting, setRedirecting] = useState(false);
  const [feishuError, setFeishuError] = useState("");
  const feedback = useRef<HTMLParagraphElement>(null);
  const message = error || feishuError || failure || loadError;

  useEffect(() => {
    if (phase === "error") feedback.current?.focus();
  }, [phase]);

  if (location.search || location.hash) {
    return <Navigate to={paths.login} state={state} replace />;
  }
  if (phase === "ready") return <Navigate to={getLoginDestination(state)} replace />;

  async function feishuLogin() {
    if (redirecting) return;
    setRedirecting(true);
    setFeishuError("");
    try {
      // 回跳地址存在后端登录流程中，登录页地址不附加参数
      const { url } = await startFeishuLogin(getLoginDestination(state));
      window.location.assign(url);
    } catch (failure) {
      setFeishuError(failure instanceof Error ? failure.message : "无法发起飞书登录，请稍后重试");
      setRedirecting(false);
    }
  }

  const passwordForm = (
    <PasswordLoginForm
      busy={busy}
      error={error}
      onSubmit={(username, password) => void signIn(username, password)}
    />
  );

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
          aria-busy={busy || redirecting || phase === "loading"}
          aria-labelledby="identity-title"
        >
          <header className="identity-login__heading">
            <h1 id="identity-title">登录工作台</h1>
            <p>使用公司飞书账号登录，权限按你所在部门开通。</p>
          </header>
          {message && (
            <p
              id="identity-feedback"
              className="identity-login__feedback"
              ref={feedback}
              tabIndex={-1}
              role="alert"
            >
              {message}
            </p>
          )}
          {phase === "loading" || (phase === "login" && !options && !loadError) ? (
            <div className="identity-login__state" role="status">
              <span className="identity-login__spinner" aria-hidden="true" />
              <strong>{phase === "loading" ? "正在检查登录状态…" : "正在读取登录方式…"}</strong>
              <p>请稍候。</p>
            </div>
          ) : phase === "error" ? (
            <div className="identity-login__state">
              <p>暂时无法确认登录状态，请检查连接后重试。</p>
              <Button onClick={retry}>重新检查会话</Button>
            </div>
          ) : options?.feishu ? (
            <>
              <Button
                className="identity-login__submit identity-login__feishu"
                variant="primary"
                disabled={redirecting || busy}
                onClick={() => void feishuLogin()}
              >
                {redirecting ? "正在跳转飞书…" : "使用飞书登录"}
              </Button>
              {options.password && (
                <details className="identity-login__fallback">
                  <summary>管理员应急登录</summary>
                  <p>仅在飞书登录不可用时使用。</p>
                  {passwordForm}
                </details>
              )}
            </>
          ) : options?.password ? (
            <>
              <p className="identity-login__notice">飞书登录尚未配置，可使用管理员账号登录。</p>
              {passwordForm}
            </>
          ) : (
            <p className="identity-login__notice">登录方式尚未配置，请联系系统管理员。</p>
          )}
          <p className="identity-login__help">无法登录或权限不对，请联系系统管理员。</p>
        </section>
        <p className="identity-access__note">工作台登录与 NetSuite、柠檬云账号独立。</p>
      </div>
    </main>
  );
}
