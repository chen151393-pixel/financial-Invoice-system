import { StatCard, StatGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { ReceivableTotal } from "../types";

/** 报关应收汇概况：每个币种的合计、两条路径应收与待处理金额，全部取后端合计，不在前端加总。 */
export function ReceivableStats({ totals }: { totals: ReceivableTotal[] }) {
  if (!totals.length) return null;
  const currencies = [...new Set(totals.map((total) => total.currency))];
  return (
    <StatGrid label="应收汇概况">
      {currencies.flatMap((currency) => {
        const pick = (route: ReceivableTotal["route"]) =>
          totals.find((total) => total.currency === currency && total.route === route);
        const all = pick("all");
        const hk = pick("hk_transit");
        const direct = pick("direct");
        return [
          all && (
            <StatCard
              key={`all-${currency}`}
              glyph="总"
              tone="primary"
              label={`报关应收汇（总）（${currency}）`}
              value={money(all.amount)}
              note={`${all.count} 票 · 未收 ${money(all.outstandingAmount)}`}
            />
          ),
          hk && (
            <StatCard
              key={`hk-${currency}`}
              glyph="港"
              tone="primary"
              label={`香港中转应收汇（${currency}）`}
              value={money(hk.amount)}
              note={`${hk.count} 票 · 已到账 ${money(hk.receivedAmount)}`}
            />
          ),
          direct && (
            <StatCard
              key={`direct-${currency}`}
              glyph="直"
              tone="neutral"
              label={`直接收汇应收汇（${currency}）`}
              value={money(direct.amount)}
              note={`${direct.count} 票 · 已收 ${money(direct.receivedAmount)}（推算）`}
            />
          ),
          hk && (
            <StatCard
              key={`pending-${currency}`}
              glyph="待"
              tone="warning"
              label={`香港中转待登记回款（${currency}）`}
              value={money(hk.pendingAmount)}
              note={`${hk.pendingCount} 票尚未建批次`}
            />
          ),
          direct && (
            <StatCard
              key={`outstanding-${currency}`}
              glyph="收"
              tone="warning"
              label={`直接收汇待收金额（${currency}）`}
              value={money(direct.outstandingAmount)}
              note={
                direct.overpaidAmount !== "0.00"
                  ? `推算 · 另有超收 ${money(direct.overpaidAmount)}`
                  : "先出口先冲抵推算"
              }
            />
          ),
        ];
      })}
    </StatGrid>
  );
}
