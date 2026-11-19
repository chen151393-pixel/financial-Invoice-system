import { StatCard, StatGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { CurrencyTotal, LedgerTotal, RouteTotal } from "../types";

/** 报关金额按当前查询汇总，直接收汇待收金额取总账。 */
export function ReceivableStats({
  totals,
  combinedTotals,
  unsettled,
  directTotals,
}: {
  totals: RouteTotal[];
  combinedTotals: CurrencyTotal[];
  unsettled: RouteTotal[];
  directTotals?: LedgerTotal[] | null;
}) {
  const pending = unsettled.filter((total) => total.route === "hk_transit");
  if (!totals.length && !directTotals?.length && directTotals !== null) return null;
  return (
    <StatGrid label="应收汇概况">
      {combinedTotals.map((total) => (
        <StatCard
          key={`combined-${total.currency}`}
          glyph="总"
          tone="primary"
          label={`报关应收汇（总）（${total.currency}）`}
          value={money(total.amount)}
          note={`${total.count} 票 · 香港中转 + 直接收汇`}
        />
      ))}
      {totals.map((total) => (
        <StatCard
          key={`${total.route}-${total.currency}`}
          glyph={total.route === "hk_transit" ? "港" : "直"}
          tone={total.route === "hk_transit" ? "primary" : "neutral"}
          label={`${total.routeLabel}应收汇（${total.currency}）`}
          value={money(total.amount)}
          note={`${total.count} 票 · ${total.route === "hk_transit" ? "进香港中转批次登记" : "进直接收汇明细"}`}
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
      {directTotals?.map((total) => (
        <StatCard
          key={`direct-outstanding-${total.currency}`}
          glyph="收"
          tone="warning"
          label={`直接收汇待收金额（${total.currency}）`}
          value={money(total.outstanding)}
          note="直接收汇总账 · 按收货人汇总未收余额"
        />
      ))}
      {directTotals === null && (
        <StatCard glyph="收" tone="warning" label="直接收汇待收金额" value="—" note="暂时无法读取总账" />
      )}
    </StatGrid>
  );
}
