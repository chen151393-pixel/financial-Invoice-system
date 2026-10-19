import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { paths, syncBatchPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { useBackgroundConfig } from "../hooks/useBackgroundConfig";
import { SyncBatchForm } from "../components/SyncBatchForm";
import { SyncPlanForm } from "../components/SyncPlanForm";
import "../components/sync-background.css";

export function LemonBackgroundPanel() {
  const state = useBackgroundConfig();
  const navigate = useNavigate();
  const [tab, setTab] = useState("manual");
  return (
    <section className="sync-background" aria-label="柠檬云后台同步">
      <div className="sync-background__heading">
        <div>
          <h2>全部账套 · 后台同步</h2>
          <p>统一配置同步范围，按账套查看真实执行结果。</p>
        </div>
        <Link to={paths.sync}>查看执行记录</Link>
      </div>
      {state.error && (
        <p role="alert" className="sync-background__error">
          {state.error}
        </p>
      )}
      {state.message && <p role="status">{state.message}</p>}
      {!state.data && !state.error && <p role="status">正在读取同步计划…</p>}
      {!state.data && state.error && <Button onClick={() => void state.refresh()}>重新加载</Button>}
      {state.data && (
        <>
          <p className="sync-background__notice">{state.data.coverage}</p>
          {!state.data.submit.allowed && (
            <p role="alert">
              {state.data.submit.reason}{" "}
              <Button disabled={Boolean(state.busy)} onClick={() => void state.refresh()}>
                刷新授权状态
              </Button>
            </p>
          )}
          <div className="sync-background__tabs" aria-label="同步配置方式">
            <Button
              aria-pressed={tab === "manual"}
              onClick={() => setTab("manual")}
              disabled={Boolean(state.busy)}
            >
              手动补拉
            </Button>
            <Button
              aria-pressed={tab === "plan"}
              onClick={() => setTab("plan")}
              disabled={Boolean(state.busy)}
            >
              定时计划
            </Button>
          </div>
          {tab === "manual" ? (
            <SyncBatchForm
              data={state.data}
              accounts={state.accounts}
              busy={Boolean(state.busy)}
              query={() => void state.query()}
              submit={(body) => void state.submit(body, (id) => navigate(syncBatchPath(id)))}
            />
          ) : (
            <SyncPlanForm
              key={state.data.plan.revision}
              data={state.data}
              accounts={state.accounts}
              busy={Boolean(state.busy)}
              query={() => void state.query()}
              save={(plan) => void state.save(plan)}
            />
          )}
        </>
      )}
    </section>
  );
}
