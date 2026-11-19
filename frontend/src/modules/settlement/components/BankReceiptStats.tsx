import { Alert, StatCard, StatGrid } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BankReceiptTotal } from "../types";

/** 主体归属、补零及合计由后端提供；不从明细当前页汇总，不按账套编号分组。 */
export function BankReceiptStats({ totals }: { totals: BankReceiptTotal[] }) {
  const featured = totals.filter((total) => total.featuredCompany);
  const others = totals.filter((total) => !total.featuredCompany);
  return (
    <>
      <StatGrid label="按收款抬头汇总">
        {featured.map((total) => (
          <StatCard
            key={`${total.receivingCompany}-${total.currency}`}
            glyph="汇"
            tone="primary"
            label={total.receivingCompany}
            value={money(total.amount)}
            note={`${total.currency} · ${
              total.count === 0
                ? "当前条件下暂无收汇记录"
                : total.thirdPartyCount > 0
                  ? `${total.count} 笔 · 其中三方代付 ${total.thirdPartyCount} 笔 ${money(total.thirdPartyAmount)}`
                  : `${total.count} 笔`
            }`}
          />
        ))}
      </StatGrid>
      {others.length > 0 && (
        <Alert title="其他收款抬头">
          {others
            .map(
              (total) =>
                `${total.receivingCompany}：${total.currency} ${money(total.amount)}（${total.count} 笔）`,
            )
            .join("；")}
        </Alert>
      )}
    </>
  );
}
