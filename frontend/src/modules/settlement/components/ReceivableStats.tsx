import { StatCard, StatGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { RouteTotal } from "../types";

/** 报关应收汇概况：金额与张数全部来自后端汇总（随查询条件变化），按回款路径与币种分开。 */
export function ReceivableStats({ totals, unsettled }: { totals: RouteTotal[]; unsettled: RouteTotal[] }) {
  const pending = unsettled.filter((total) => total.route === "hk_transit");
  if (!totals.length) return null;
  return (
    <StatGrid label="应收汇概况">
      {totals.map((total) => (
        <StatCard
          key={`${total.route}-${total.currency}`}
          glyph={total.route === "hk_transit" ? "港" : "直"}
          tone={total.route === "hk_transit" ? "primary" : "neutral"}
          label={`${total.routeLabel}应收汇（${total.currency}）`}
          value={money(total.amount)}
          note={`${total.count} 票 · ${total.route === "hk_transit" ? "登记回款建批次" : "进直接收汇明细"}`}
        />
      ))}
      {pending.map((total) => (
        <StatCard
          key={`pending-${total.currency}`}
          glyph="待"
          tone="warning"
          label={`香港中转待登记回款（${total.currency}）`}
          value={money(total.amount)}
          note={`${total.count} 票尚未建批次`}
        />
      ))}
    </StatGrid>
  );
}
