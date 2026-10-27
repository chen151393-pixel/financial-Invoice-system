import { Button } from "../../../shared/components/Button";
import { WorkbenchKpis } from "../components/WorkbenchKpis";
import { WorkbenchMetrics } from "../components/WorkbenchMetrics";
import { WorkbenchSuppliers } from "../components/WorkbenchSuppliers";
import { WorkbenchTodos } from "../components/WorkbenchTodos";
import { WorkbenchToolbar } from "../components/WorkbenchToolbar";
import { WorkbenchTrend } from "../components/WorkbenchTrend";
import type { useWorkbench } from "../hooks/useWorkbench";
import "../components/workbench.css";

export function WorkbenchPage({ state }: { state: ReturnType<typeof useWorkbench> }) {
  return (
    <div className="wb">
      <WorkbenchToolbar state={state} />
      {state.loading && (
        <div className="wb-panel wb-loading" role="status">
          正在读取工作台数据…<p>正在汇总财务核对、发票比对和开票跟进。</p>
        </div>
      )}
      {state.error && (
        <div className="wb-panel wb-empty" role="alert">
          <strong>工作台暂时无法加载</strong>
          <p>{state.error}</p>
          <Button onClick={state.refresh}>重新加载</Button>
          {(state.query.trendStart || state.query.trendEnd) && (
            <Button onClick={() => state.change({ trendStart: null, trendEnd: null })}>
              恢复默认开票日期
            </Button>
          )}
        </div>
      )}
      {state.data && (
        <>
          <WorkbenchKpis data={state.data} />
          {/* 业务流程与供应商待收票并排，窄屏上下排列 */}
          <div className="wb-columns">
            <WorkbenchMetrics
              stages={state.data.stages ?? []}
              noTaskCount={state.data.noTaskCount ?? 0}
              query={state.query}
            />
            <aside className="wb-aside" aria-label="收票情况">
              <WorkbenchSuppliers data={state.data} />
            </aside>
          </div>
          <WorkbenchTrend data={state.data} change={state.change} />
          {state.exportNotice && (
            <p className="wb-feedback" role="status">
              {state.exportNotice}
            </p>
          )}
          <WorkbenchTodos
            data={state.data}
            query={state.query}
            change={state.change}
            exporting={state.exporting}
            onExport={() => void state.download()}
          />
          <details className="wb-definitions">
            <summary>统计口径</summary>
            <p>
              业务状态分区按报关单计数：待审核的为“待审批”，其余取报关单下当前任务中最慢的阶段（待通知开票 →
              待核票 → 资料已回 →
              开票完成）；没有开票任务（供应商均关闭通知）的为“无需开票”，不进分区。待办表中待核对以报关单计数；比对待办按发票与采购账套计数，含待审核建议与待复核分配；待开票以未完成、未被替代的任务计数。不同类型可能涉及同一业务，合计为待办事项数，不是唯一单据数。
            </p>
            <p>
              报关单可能共享子采购行，工作台不重复汇总应开金额；进入核对页查看明细。待收金额沿用任务逐行扣减有效收票的口径，未知值以“—”展示，各币种独立统计。
            </p>
            <p>
              流程：同步报关与子采购 → 财务审核 → 准备合同并通知供应商 → 导入进项发票 → 人工比对审核 →
              自动更新任务收票进度。页面查询和导出不触发审核、通知或 NS 写入。
            </p>
          </details>
        </>
      )}
    </div>
  );
}
