import type { InvoiceTotals } from "../../matching/api";
import { MetricCard, MetricGrid, type IconName } from "../../../shared/components/ui";
import { money } from "./format";

const metrics = [
  { label: "价税合计", field: "gross", count: "count", icon: "amount" },
  { label: "票面税额", field: "tax", count: "count", icon: "invoice" },
  { label: "待匹配金额", field: "pendingAmount", count: "pendingCount", icon: "clock" },
  { label: "待复核金额", field: "reviewAmount", count: "reviewCount", icon: "alert" },
] as const satisfies readonly { label: string; field: string; count: string; icon: IconName }[];

type Props = { data: InvoiceTotals | null; loading: boolean; error: string };

/** 当前筛选汇总：金额与张数为后端全范围统计；各币种分行显示，未知金额显示"—"，不冒充零。 */
export function InvoiceSummary({ data, loading, error }: Props) {
  return (
    <section className="invoice-list__summary" aria-label="当前筛选汇总" aria-busy={loading}>
      <MetricGrid>
        {metrics.map(({ label, field, count, icon }) => {
          const unavailable = loading || error || !data;
          const amounts = data?.amounts ?? [];
          return (
            <MetricCard
              key={field}
              label={label}
              icon={icon}
              value={
                unavailable ? (
                  "—"
                ) : amounts.length === 0 ? (
                  "0.00"
                ) : (
                  <span className="invoice-list__amounts">
                    {amounts.map((amount) => (
                      <span key={amount.currency}>
                        {amount.currency === "CNY" ? "¥ " : `${amount.currency} `}
                        {money(amount[field])}
                      </span>
                    ))}
                  </span>
                )
              }
              hint={
                unavailable ? (
                  loading ? (
                    "正在统计…"
                  ) : (
                    "统计读取失败，请刷新数据"
                  )
                ) : amounts.length === 0 ? (
                  "当前筛选无发票"
                ) : (
                  <span className="invoice-list__amounts">
                    {amounts.map((amount) => (
                      <span key={amount.currency}>
                        {amount.currency} · {amount[count]} 张发票
                      </span>
                    ))}
                  </span>
                )
              }
            />
          );
        })}
      </MetricGrid>
    </section>
  );
}
