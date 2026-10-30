import { useState } from "react";
import { Alert, Button, ErrorState, Skeleton } from "../../../shared/components/ui";
import { NsManualPull } from "../NsManualPull";
import { NsPlanBatches } from "../components/NsPlanBatches";
import { NsPlanForm } from "../components/NsPlanForm";
import { NsSyncStatus } from "../components/NsSyncStatus";
import { SyncTabs, type SyncTab } from "../components/SyncTabs";
import { useNsPlan } from "../hooks/useNsPlan";
import "../components/sync-background.css";
import "../components/sync-layout.css";

/**
 * NS 数据同步页，与柠檬云页同一结构：状态条 →“手动补拉 / 定时计划”页签 → 计划执行记录。
 * 手动补拉面板切走时只隐藏不卸载，不中断正在进行的拉取；启用条件、校验和执行均在后端。
 */
export function NsSyncPanel() {
  const state = useNsPlan();
  const { data } = state;
  const [tab, setTab] = useState<SyncTab>("manual");
  return (
    <div className="sync-background__stack">
      {data && <NsSyncStatus data={data} />}
      <section
        className="sync-background sync-background--flush"
        aria-label="NS 单据同步"
        aria-busy={state.busy}
      >
        <div className="sync-background__head">
          <div className="sync-background__title">
            <h2>报关单与子采购单</h2>
            <small>只读 NS 正式环境，不写入 NS</small>
          </div>
        </div>
        <SyncTabs value={tab} onChange={setTab} disabled={state.busy} />
        <div className="sync-background__manual" hidden={tab !== "manual"}>
          <NsManualPull />
        </div>
        <div hidden={tab !== "plan"}>
          {(state.error || state.message || !data || !data.submit.allowed) && (
            <div className="sync-background__body">
              {state.error &&
                (data ? (
                  <Alert tone="danger">{state.error}</Alert>
                ) : (
                  <ErrorState
                    title="同步计划读取失败"
                    message={state.error}
                    action={<Button onClick={() => void state.refresh()}>重新读取</Button>}
                  />
                ))}
              {!data && !state.error && <Skeleton label="正在读取同步计划" />}
              {state.message && <Alert tone="success">{state.message}</Alert>}
              {data && !data.submit.allowed && (
                <Alert tone="warning" title="当前不能启用定时同步">
                  {data.submit.reason}{" "}
                  <Button size="sm" disabled={state.busy} onClick={() => void state.refresh()}>
                    重新检查配置
                  </Button>
                </Alert>
              )}
            </div>
          )}
          {data && (
            <NsPlanForm
              key={data.plan.revision}
              data={data}
              busy={state.busy}
              save={(value) => void state.save(value)}
            />
          )}
        </div>
      </section>
      <NsPlanBatches />
    </div>
  );
}
