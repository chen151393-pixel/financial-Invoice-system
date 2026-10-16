import { Button } from "../../shared/components/Button";
import type { useLemonBinding } from "./useLemonBinding";

type Props = ReturnType<typeof useLemonBinding> & { invalidCallback: boolean };

export function LemonBindingView({
  data,
  mobile,
  password,
  busy,
  error,
  setMobile,
  setPassword,
  run,
  refresh,
  invalidCallback,
}: Props) {
  return (
    <section
      className="lemon-binding"
      aria-busy={Boolean(busy) || (!data && !error)}
      aria-labelledby="lemon-binding-title"
    >
      <header className="lemon-binding__heading">
        <div>
          <h2 id="lemon-binding-title">绑定已有柠檬云账号</h2>
          <p>将已有账号关联到本系统的柠檬云应用。</p>
        </div>
        <Button disabled={Boolean(busy)} onClick={refresh}>
          刷新状态
        </Button>
      </header>
      {invalidCallback && (
        <p className="lemon-binding__warning" role="alert">
          本次回调无效、已使用或已过期。请查看当前状态；尚未绑定时可重新授权。
        </p>
      )}
      {error && (
        <p className="lemon-binding__warning" role="alert">
          {error}
        </p>
      )}
      {!data && !error && (
        <p className="lemon-binding__loading" role="status">
          正在读取绑定配置…
        </p>
      )}
      {data && (
        <>
          <div className="lemon-binding__workspace">
            <div className="lemon-binding__operation">
              <p role="status" className="lemon-binding__status">
                {data.message}
              </p>
              {data.mobile && <p>已有账号：{data.mobile}</p>}
              {data.verifiedAt && (
                <p>
                  最近确认：{new Date(data.verifiedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
                  （北京时间）
                </p>
              )}
              {data.confirm.allowed ? (
                <form
                  noValidate
                  className="lemon-binding__form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run("confirm");
                  }}
                >
                  <p>
                    请核对即将绑定的账号：<strong>{data.confirmationMobile}</strong>
                  </p>
                  <label htmlFor="lemon-binding-password">
                    柠檬云账号密码
                    <input
                      id="lemon-binding-password"
                      type="password"
                      autoComplete="off"
                      value={password}
                      disabled={Boolean(busy)}
                      aria-describedby="lemon-password-help"
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  <p id="lemon-password-help">
                    官方绑定接口需要账号密码。密码仅用于本次绑定，不保存到数据库或浏览器存储。
                  </p>
                  <Button type="submit" variant="primary" disabled={Boolean(busy)}>
                    {busy === "confirm" ? "正在确认绑定…" : "确认绑定此账号"}
                  </Button>
                </form>
              ) : data.begin.allowed ? (
                <form
                  noValidate
                  className="lemon-binding__form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run("start");
                  }}
                >
                  <label htmlFor="lemon-binding-mobile">
                    柠檬云账号手机号
                    <input
                      id="lemon-binding-mobile"
                      type="tel"
                      autoComplete="tel"
                      value={mobile}
                      placeholder="输入已有账号的手机号"
                      disabled={Boolean(busy)}
                      aria-describedby="lemon-mobile-help"
                      onChange={(event) => setMobile(event.target.value)}
                    />
                  </label>
                  <p id="lemon-mobile-help">
                    {data.phase === "unbound" ? "下一步将在柠檬云官方页面登录并授权。" : data.begin.reason}
                  </p>
                  <Button type="submit" variant="primary" disabled={Boolean(busy)}>
                    {busy === "start" ? "正在前往柠檬云…" : "前往柠檬云授权"}
                  </Button>
                </form>
              ) : (
                data.begin.reason !== data.message && (
                  <p className="lemon-binding__warning">{data.begin.reason}</p>
                )
              )}
              {data.verify.allowed && (
                <div className="lemon-binding__verify">
                  <Button disabled={Boolean(busy)} onClick={() => void run("verify")}>
                    {busy === "verify" ? "正在核实…" : "核实已有绑定"}
                  </Button>
                  <p>{data.verify.reason}</p>
                </div>
              )}
              {!data.verify.allowed &&
                data.verify.reason !== data.begin.reason &&
                data.phase !== "unbound" && <p>{data.verify.reason}</p>}
              <details
                className="lemon-binding__configuration"
                open={data.phase === "unbound" && !data.begin.allowed}
              >
                <summary>查看管理员配置说明</summary>
                <ol>
                  <li>向柠檬云申请应用编号和密钥，说明需要开通的系统权限。</li>
                  <li>在服务器配置应用编号、密钥和 HTTPS 回调地址。</li>
                  <li>联系柠檬云登记回调地址，重启服务后刷新本页状态。</li>
                </ol>
                <p>当前配置的回调地址（是否已登记需管理员向柠檬云核实）：</p>
                <p className="lemon-binding__callback">{data.redirectUri || "尚未配置回调地址"}</p>
                <p>应用密钥在服务器配置，无需在此页面填写。</p>
              </details>
            </div>
            <aside className="lemon-binding__guide" aria-labelledby="lemon-guide-title">
              <h3 id="lemon-guide-title">已有账号如何授权？</h3>
              <ol>
                <li>
                  <strong>填写已有账号</strong>
                  <p>使用柠檬云账号的手机号，无需重新注册。</p>
                </li>
                <li>
                  <strong>前往柠檬云登录</strong>
                  <p>在官方授权页输入密码，登录后自动返回本系统。</p>
                </li>
                <li>
                  <strong>返回后确认绑定</strong>
                  <p>核对账号并提交密码，由系统完成关联；以返回的绑定状态为准。</p>
                </li>
              </ol>
              <a href="https://open2.ningmengyun.com/Home/AccountAuthLink" target="_blank" rel="noreferrer">
                查看官方绑定说明（新窗口）
              </a>
            </aside>
          </div>
          <footer className="lemon-binding__boundary">
            <div>
              <strong>发票数据接入</strong>
              <p>{data.sync.reason}</p>
            </div>
            <a className="ui-button ui-button--secondary" href="#lemon-invoice-import">
              前往 Excel 导入
            </a>
          </footer>
        </>
      )}
    </section>
  );
}
