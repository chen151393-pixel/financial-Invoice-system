import { Progress } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Workbench } from "../types/workbench";

const symbol = (currency: string) => (currency === "CNY" ? "¥" : currency);

/** 供应商待收票排行：金额、条长比例、最长等待天数与是否超期（> 15 天）都来自后端，人民币在前。 */
export function WorkbenchSuppliers({ data }: { data: Workbench }) {
  return (
    <section className="wb-panel" aria-labelledby="wb-suppliers-title">
      <div className="wb-panel__head">
        <div>
          <h2 id="wb-suppliers-title">供应商待收票排行</h2>
          <p className="wb-panel__sub">按待收金额 · 橙色为最长等待超过 15 天</p>
        </div>
      </div>
      {data.suppliers.length ? (
        <ol className="wb-rank-list">
          {data.suppliers.map((row, index) => (
            <li className="wb-rank" key={row.key}>
              <div className="wb-rank__head">
                <span className="wb-rank__no">{index + 1}</span>
                <strong>{row.supplier}</strong>
                <span className="wb-rank__amount">
                  {symbol(row.currency)} {money(row.amount)}
                </span>
              </div>
              <div className="wb-rank__bar">
                <Progress
                  width={row.percent}
                  label={`${row.supplier} 待收票 ${symbol(row.currency)} ${money(row.amount)}`}
                  tone={row.overdue ? "warning" : "info"}
                />
                <span className={row.overdue ? "wb-rank__days is-overdue" : "wb-rank__days"}>
                  最长 {row.longestDays} 天
                </span>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="wb-empty">
          <strong>暂无可排名的待收票金额</strong>
          <p>仅展示金额和币种完整的供应商。</p>
        </div>
      )}
      {data.unknownSupplierAmounts > 0 && (
        <p className="wb-report-note">
          另有 {data.unknownSupplierAmounts} 组供应商因金额或币种不完整，未纳入排名。
        </p>
      )}
    </section>
  );
}
