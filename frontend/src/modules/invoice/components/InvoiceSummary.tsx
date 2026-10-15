import type { InvoiceListResult } from "../types/invoice";
import { money } from "./format";

export function InvoiceSummary({ data, loading }: { data: InvoiceListResult | null; loading: boolean }) {
  return (
    <section className="invoice-list__summary" aria-label="当前筛选汇总">
      <div className="invoice-list__metric">
        <span>价税合计</span>
        {data && data.amounts.length > 0 ? (
          data.amounts.map((amount) => (
            <div key={amount.currency}>
              <strong>
                {amount.currency === "CNY" ? "¥ " : `${amount.currency} `}
                {money(amount.gross)}
              </strong>
              <small>
                {amount.currency} · {amount.count} 张发票
              </small>
            </div>
          ))
        ) : (
          <>
            <strong>—</strong>
            <small>{data ? "当前筛选无发票" : loading ? "正在读取" : "读取失败"}</small>
          </>
        )}
      </div>
      {["可抵扣税额", "待匹配金额", "异常金额"].map((label) => (
        <div className="invoice-list__metric" key={label}>
          <span>{label}</span>
          <strong>—</strong>
          <small>对应业务数据尚未接入</small>
        </div>
      ))}
    </section>
  );
}
