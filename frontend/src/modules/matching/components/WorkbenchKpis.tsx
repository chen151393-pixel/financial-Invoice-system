import { Badge, MetricCard, MetricGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Kpi } from "../types/workbench";
import { roleLabels } from "../types/workbench";

/**
 * 工作台关键指标：数值、对比说明、提示与近 6 个月走势全部来自后端；第一张为主指标（主色实底）。
 * 金额只格式化后端十进制字符串，走势线只用于画形状。
 */
export function WorkbenchKpis({ kpis }: { kpis: Kpi[] }) {
  return (
    <MetricGrid label="关键指标">
      {kpis.map((kpi, index) => (
        <MetricCard
          key={kpi.key}
          featured={index === 0 ? "solid" : undefined}
          label={kpi.label}
          value={kpi.currency === "CNY" ? `¥ ${money(kpi.value)}` : kpi.value}
          unit={kpi.unit || undefined}
          badge={
            <Badge dot={false} tone={kpi.role === "finance" ? "info" : "warning"}>
              {roleLabels[kpi.role]}
            </Badge>
          }
          delta={{ text: kpi.delta, direction: kpi.direction, tone: kpi.tone }}
          hint={kpi.hint}
          sparkline={kpi.series.map(Number)}
        />
      ))}
    </MetricGrid>
  );
}
