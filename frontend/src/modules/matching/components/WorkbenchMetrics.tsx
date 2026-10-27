import { Link } from "react-router";
import { reviewListPath, taskListPath } from "../../../app/paths";
import { HorizontalBarChart } from "../../../shared/components/ui";
import type { Workbench } from "../types/workbench";
import "./workbench-metrics.css";

/**
 * 业务流程漏斗：后端按报关单给出六步"至少走到这一步"的计数、上一环节通过率、整体完结率，
 * 以及卡在上一步的分项（待财务审核或开票跟进节点），分项链接进入对应列表。横向条形只负责展示计数。
 */
export function WorkbenchMetrics({
  funnel,
  noTaskCount,
}: {
  funnel: NonNullable<Workbench["funnel"]>;
  noTaskCount: number;
}) {
  const colors = [
    "var(--color-primary-strong)",
    "var(--color-primary)",
    "color-mix(in srgb, var(--color-primary) 85%, var(--color-surface))",
    "var(--color-chart-2)",
    "color-mix(in srgb, var(--color-chart-2) 70%, var(--color-surface))",
    "var(--color-chart-3)",
  ];
  return (
    <section className="wb-panel" aria-labelledby="wb-flow-title">
      <div className="wb-panel__head wb-panel__head--split">
        <div>
          <h2 id="wb-flow-title">业务流程漏斗</h2>
          <p className="wb-panel__sub">报关单从入库到资料齐全完结，各环节通过量与停留量</p>
        </div>
        <span className="wb-flow__rate">
          整体完结率 <strong>{funnel.completionRate === null ? "—" : `${funnel.completionRate}%`}</strong>
        </span>
      </div>
      <div className="wb-flow">
        <HorizontalBarChart
          label="业务流程横向条形图"
          items={funnel.steps.map((step, index) => ({
            key: step.key,
            label: step.label,
            value: step.count,
            text: String(step.count),
            color: colors[index],
            note: (
              <span className="wb-flow__note">
                <span>
                  {index === 0
                    ? "起点"
                    : step.rate === null
                      ? "上一环节为 0，暂无通过率"
                      : `上一环节通过 ${step.rate}%`}
                </span>
                {step.stuck.map((item) => (
                  <Link
                    key={item.key}
                    className="wb-flow__stuck"
                    to={
                      item.key === "pending_review"
                        ? reviewListPath({ status: "pending" })
                        : taskListPath({ node: item.key })
                    }
                  >
                    {item.count} 张{item.label} →
                  </Link>
                ))}
              </span>
            ),
          }))}
        />
      </div>
      {noTaskCount > 0 && (
        <p className="wb-report-note">另有 {noTaskCount} 张无需开票（供应商关闭通知），不计入漏斗。</p>
      )}
    </section>
  );
}
