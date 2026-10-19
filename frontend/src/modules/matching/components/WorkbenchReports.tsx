import { WorkbenchTrend } from "./WorkbenchTrend";
import { money } from "../../../shared/format/money";
import type { Workbench, WorkbenchQuery } from "../types/workbench";
import "./workbench-reports.css";

export function WorkbenchReports({
  data,
  change,
}: {
  data: Workbench;
  change: (patch: Partial<WorkbenchQuery>) => void;
}) {
  return (
    <div className="wb-reports">
      <WorkbenchTrend data={data} change={change} />
      <section className="wb-panel">
        <div className="wb-panel__head">
          <h2>供应商待收票金额</h2>
          <span className="wb-count">各币种 TOP 3</span>
        </div>
        <p className="wb-report-note">有效未完成任务 · 按供应商和币种分别汇总</p>
        <div className="wb-rank-list">
          {data.suppliers.map((row) => (
            <div className="wb-rank" key={row.key}>
              <div>
                <strong>{row.supplier}</strong>
                <span>
                  {row.currency} {money(row.amount)}
                </span>
              </div>
              <div
                className="wb-track"
                role="img"
                aria-label={`${row.supplier} 待收票 ${row.currency} ${money(row.amount)}`}
              >
                <span style={{ width: `${row.percent}%` }} />
              </div>
            </div>
          ))}
        </div>
        {!data.suppliers.length && (
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
    </div>
  );
}
