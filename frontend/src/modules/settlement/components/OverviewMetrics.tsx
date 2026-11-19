import { MetricCard, MetricGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { OverviewAmounts, OverviewTotal } from "../types/overview";

const METRICS = [
  { key: "declaredTotal", label: "报关应收汇（总）" },
  { key: "receivedTotal", label: "实收汇金额（总）" },
  { key: "outstanding", label: "未收汇金额（总）" },
] as const satisfies readonly { key: keyof OverviewAmounts; label: string }[];

/** 三项金额与路径拆分直接展示后端汇总；不以当前页或批次状态推算实收。 */
export function OverviewMetrics({ total }: { total: OverviewTotal }) {
  return (
    <MetricGrid label={`${total.currency} 收汇总览`}>
      {METRICS.map((metric) => (
        <MetricCard
          key={metric.key}
          label={metric.label}
          value={money(total[metric.key])}
          unit={total.currency}
          hint={metric.key === "outstanding" ? "应收减实收；负数表示超收" : "累计金额"}
          footer={
            <span className="settlement-overview-breakdown">
              {total.routes.map((route) => (
                <span key={route.route}>
                  <span>{route.routeLabel}</span>
                  <strong>{money(route[metric.key])}</strong>
                </span>
              ))}
            </span>
          }
        />
      ))}
    </MetricGrid>
  );
}
