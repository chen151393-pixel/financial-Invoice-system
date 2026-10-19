import type { InvoiceTotals } from "../../matching/api";
import { money } from "./format";

const metrics = [
  { label: "价税合计", field: "gross", count: "count", help: "当前筛选的全部发票，包含红字金额" },
  { label: "票面税额", field: "tax", count: "count", help: "票面税额合计，不代表可抵扣税额" },
  {
    label: "待匹配金额",
    field: "pendingAmount",
    count: "pendingCount",
    help: "正常发票金额减有效确认金额，含待复核部分",
  },
  {
    label: "待复核金额",
    field: "reviewAmount",
    count: "reviewCount",
    help: "已确认但失效或待复核的分配金额",
  },
] as const;

type Props = { data: InvoiceTotals | null; loading: boolean; error: string };

export function InvoiceSummary({ data, loading, error }: Props) {
  return (
    <section className="invoice-list__summary" aria-label="当前筛选汇总" aria-busy={loading}>
      {metrics.map(({ label, field, count, help }) => (
        <div className="invoice-list__metric" key={field}>
          <span>{label}</span>
          {loading || error || !data ? (
            <>
              <strong>—</strong>
              <small>{loading ? "正在统计…" : "统计读取失败，请刷新数据"}</small>
            </>
          ) : data.amounts.length === 0 ? (
            <>
              <strong>0.00</strong>
              <small>当前筛选无发票</small>
            </>
          ) : (
            data.amounts.map((amount) => (
              <div key={amount.currency}>
                <strong>
                  {amount.currency === "CNY" ? "¥ " : `${amount.currency} `}
                  {money(amount[field])}
                </strong>
                <small>
                  {amount.currency} · {amount[count]} 张发票
                </small>
              </div>
            ))
          )}
          <small className="invoice-list__metric-help">{help}</small>
        </div>
      ))}
    </section>
  );
}
