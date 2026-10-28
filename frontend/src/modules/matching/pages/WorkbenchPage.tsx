import { Button } from "../../../shared/components/Button";
import { WorkbenchKpis } from "../components/WorkbenchKpis";
import { WorkbenchMetrics } from "../components/WorkbenchMetrics";
import { WorkbenchNodes } from "../components/WorkbenchNodes";
import { WorkbenchQueue } from "../components/WorkbenchQueue";
import { WorkbenchReceipts } from "../components/WorkbenchReceipts";
import { WorkbenchSuppliers } from "../components/WorkbenchSuppliers";
import { WorkbenchTodos } from "../components/WorkbenchTodos";
import { WorkbenchUnboundNotify } from "../components/WorkbenchUnboundNotify";
import type { useWorkbench } from "../hooks/useWorkbench";
import "../components/workbench.css";
import "../components/workbench-reports.css";

/**
 * 财务 · 采购总体工作台：关键指标 → 业务流程漏斗 → 应开与已收趋势 + 节点分布 → 供应商待收排行 + 比对队列 → 优先处理。
 * 所有数字来自后端，页面只排版；查询和导出不触发审核、通知或 NS 写入。
 */
export function WorkbenchPage({ state }: { state: ReturnType<typeof useWorkbench> }) {
  return (
    <div className="wb">
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
        </div>
      )}
      {state.data && (
        <>
          <WorkbenchKpis kpis={state.data.kpis} />
          {state.data.unboundNotify && <WorkbenchUnboundNotify data={state.data.unboundNotify} />}
          {state.data.funnel && (
            <WorkbenchMetrics funnel={state.data.funnel} noTaskCount={state.data.noTaskCount} />
          )}
          <div className="wb-columns">
            <WorkbenchReceipts monthly={state.data.monthly} />
            {state.data.nodes && <WorkbenchNodes nodes={state.data.nodes} />}
          </div>
          <div className="wb-columns wb-columns--even">
            <WorkbenchSuppliers data={state.data} />
            {state.data.queue && <WorkbenchQueue queue={state.data.queue} />}
          </div>
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
              关键指标的金额只统计人民币任务：本月应开与已收票按任务生成月份（北京时间），待收金额为所有未完成任务；走势线为近
              6 个月的同口径序列。待财务审核按报关单计数，待通知供应商按开票跟进节点计数。
            </p>
            <p>
              业务流程漏斗按报关单计数：待审核的停在“财务审核”，其余取报关单下当前任务中最慢的开票跟进节点（与开票跟进页同一判定），全部任务完成为“资料齐全完结”；没有开票任务（供应商均关闭通知）的为“无需开票”，不进漏斗。节点分布按进行中的任务计数。
            </p>
            <p>
              供应商待收票按供应商、账套与币种分组，各币种取前 6
              名；金额或币种不完整的分组不参与排名。比对队列的不一致分类按待审核建议计数，一条建议可属多类。待办中不同类型可能涉及同一业务，合计为待办事项数，不是唯一单据数。
            </p>
          </details>
        </>
      )}
    </div>
  );
}
