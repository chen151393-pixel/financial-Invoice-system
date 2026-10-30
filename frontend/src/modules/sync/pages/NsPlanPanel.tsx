import { Alert, Button, ErrorState, Skeleton } from "../../../shared/components/ui";
import { NsPlanBatches } from "../components/NsPlanBatches";
import { NsPlanForm } from "../components/NsPlanForm";
import { useNsPlan } from "../hooks/useNsPlan";
import "../components/sync-background.css";
import "../components/sync-layout.css";

/** NS 页面的定时同步计划：计划表单与计划执行记录。启用条件、校验和执行均在后端。 */
export function NsPlanPanel() {
  const state = useNsPlan();
  const { data } = state;
  return (
    <div className="sync-background__stack" id="ns-plan">
      <section
        className="sync-background sync-background--flush"
        aria-label="NS 定时同步计划"
        aria-busy={state.busy}
      >
        <div className="sync-background__head">
          <div className="sync-background__title">
            <h2>定时同步计划</h2>
            <small>只读 NS 正式环境，不写入 NS</small>
          </div>
        </div>
        <div className="sync-background__body">
          {data && <p className="sync-muted">{data.coverage}</p>}
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
          {data?.plan.pausedReason && (
            <Alert tone="warning" title="计划已自动暂停">
              {data.plan.pausedReason}
            </Alert>
          )}
          {data && !data.submit.allowed && (
            <Alert tone="warning" title="当前不能启用定时同步">
              {data.submit.reason}{" "}
              <Button size="sm" disabled={state.busy} onClick={() => void state.refresh()}>
                重新检查配置
              </Button>
            </Alert>
          )}
        </div>
        {data && (
          <NsPlanForm
            key={data.plan.revision}
            data={data}
            busy={state.busy}
            save={(plan) => void state.save(plan)}
          />
        )}
      </section>
      <NsPlanBatches />
    </div>
  );
}
