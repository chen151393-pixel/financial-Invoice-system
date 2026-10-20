import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { money } from "../../../shared/format/money";
import type { Workbench, WorkbenchQuery } from "../types/workbench";
import { WorkbenchTrendRange } from "./WorkbenchTrendRange";
import "./workbench-reports.css";

export function WorkbenchTrend({
  data,
  change,
}: {
  data: Workbench;
  change: (patch: Partial<WorkbenchQuery>) => void;
}) {
  return (
    <section className="wb-panel wb-trend-panel">
      <div className="wb-panel__head">
        <h2>已开票金额趋势</h2>
        <Link to={paths.invoices}>查看进项发票 →</Link>
      </div>
      <WorkbenchTrendRange data={data} change={change} />
      {!data.trend.length && (
        <div className="wb-empty">
          <strong>所选开票日期内暂无正常发票</strong>
          <p>可调整开票日期范围；导入时间不影响本图的日期归属。</p>
        </div>
      )}
      {data.trend.map((series) => (
        <div className="wb-trend" key={series.currency}>
          <h3>{series.currency || "币种待核实"} · 金额 / 元</h3>
          {series.hasNegative && <p className="wb-caption">中线为零，向下柱表示负金额。</p>}
          <div
            className={`wb-chart${series.hasNegative ? " wb-chart--signed" : ""}${series.points.length > 10 ? " wb-chart--dense" : ""}`}
            role="list"
            aria-label={`${series.currency} 已开票金额`}
          >
            {series.points.map((point) => (
              <div
                className="wb-chart__column"
                key={point.date}
                role="listitem"
                tabIndex={series.points.length > 10 ? 0 : undefined}
                aria-label={`${point.date} ${series.currency} ${money(point.amount)}`}
              >
                <span className="wb-chart__amount">{money(point.amount)}</span>
                <div className="wb-chart__well">
                  <div className={`wb-chart__half${point.negative ? " wb-chart__half--negative" : ""}`}>
                    <span style={{ height: `${point.percent}%` }} />
                  </div>
                </div>
                <time className="wb-chart__date" dateTime={point.date}>
                  {point.date.slice(5)}
                </time>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
