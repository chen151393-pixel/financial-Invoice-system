import { useState } from "react";
import { useNavigate } from "react-router";
import { syncBatchPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { useBackgroundConfig } from "../hooks/useBackgroundConfig";
import { LemonRecentBatches } from "../components/LemonRecentBatches";
import { LemonSyncStatus } from "../components/LemonSyncStatus";
import { SyncBatchForm } from "../components/SyncBatchForm";
import { SyncPlanForm } from "../components/SyncPlanForm";
import "../components/sync-background.css";
import "../components/sync-layout.css";

const tabs = [
  ["manual", "手动补拉"],
  ["plan", "定时计划"],
] as const;

export function LemonBackgroundPanel() {
  const state = useBackgroundConfig();
  const navigate = useNavigate();
  const [tab, setTab] = useState<(typeof tabs)[number][0]>("manual");
  return (
    <>
      {state.data && <LemonSyncStatus data={state.data} />}
      <section className="sync-background sync-background--flush" aria-label="柠檬云后台同步">
        <div className="sync-background__head">
          <div className="sync-background__title">
            <h2>全部账套 · 后台同步</h2>
            {state.data && <small>{state.data.coverage}</small>}
          </div>
        </div>
        {state.data && (
          <div className="sync-tabs" role="group" aria-label="同步配置方式">
            {tabs.map(([key, label]) => (
              <button
                type="button"
                key={key}
                className="sync-tab"
                aria-pressed={tab === key}
                disabled={Boolean(state.busy)}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {(state.error || state.message || !state.data || !state.data.submit.allowed) && (
          <div className="sync-background__body">
            {state.error && (
              <p role="alert" className="sync-background__error">
                {state.error}
              </p>
            )}
            {state.message && <p role="status">{state.message}</p>}
            {!state.data && !state.error && <p role="status">正在读取同步计划…</p>}
            {!state.data && state.error && <Button onClick={() => void state.refresh()}>重新加载</Button>}
            {state.data && !state.data.submit.allowed && (
              <p role="alert" className="sync-background__error">
                {state.data.submit.reason}{" "}
                <Button disabled={Boolean(state.busy)} onClick={() => void state.refresh()}>
                  刷新授权状态
                </Button>
              </p>
            )}
          </div>
        )}
        {state.data &&
          (tab === "manual" ? (
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
          ))}
      </section>
      <LemonRecentBatches />
    </>
  );
}
