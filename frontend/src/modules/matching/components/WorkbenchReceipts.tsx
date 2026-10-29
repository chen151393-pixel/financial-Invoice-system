import { useState } from "react";
import { EmptyState, TrendChart } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Workbench } from "../types/workbench";

/**
 * 应开按关联报关单创建月（浅柱），全部正常人民币进项票按开票月汇总（深柱，含未匹配）。
 * 金额与收票／应开比来自后端；绘图只作坐标换算，展示使用后端十进制字符串。
 */
export function WorkbenchReceipts({
  monthly,
  unknownExpectedDates = 0,
}: {
  monthly: Workbench["monthly"];
  unknownExpectedDates?: number;
}) {
  const unknown = monthly.reduce((sum, item) => sum + item.unknownTasks, 0);
  const [month, setMonth] = useState("");
  const selected = monthly.find((item) => item.month === month) ?? monthly.at(-1);
  const hasAmounts = monthly.some((item) => Number(item.expected) > 0 || Number(item.received) > 0);
  return (
    <section className="wb-panel" aria-labelledby="wb-receipts-title">
      <div className="wb-panel__head wb-panel__head--split">
        <div>
          <h2 id="wb-receipts-title">应开与已收票金额趋势</h2>
          <p className="wb-panel__sub">应开按报关单创建月 · 收票按开票月 · 人民币</p>
        </div>
        {selected && hasAmounts && (
          <label className="wb-receipts-month">
            查看月份
            <select value={selected.month} onChange={(event) => setMonth(event.target.value)}>
              {monthly.map((item) => (
                <option key={item.month} value={item.month}>
                  {item.month.replace("-", "年")}月
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="wb-panel__body">
        {selected && hasAmounts && (
          <dl className="wb-receipts-summary" aria-label={`${selected.month}金额汇总`}>
            <div>
              <dt>应开金额（元）</dt>
              <dd>{money(selected.expected)}</dd>
            </div>
            <div>
              <dt>已收票金额（元）</dt>
              <dd className="wb-receipts-summary__received">{money(selected.received)}</dd>
            </div>
            <div>
              <dt>收票／应开比</dt>
              <dd>{selected.percent === null ? "—" : `${selected.percent}%`}</dd>
            </div>
          </dl>
        )}
        {hasAmounts ? (
          <TrendChart
            label="按报关单创建月的应开金额、按开票月的收票金额与收票应开比"
            height={260}
            grouped
            lineAxis="percent"
            categories={monthly.map((item) => `${Number(item.month.slice(5))}月`)}
            bars={[
              {
                key: "expected",
                label: "应开金额",
                color: "var(--color-chart-3)",
                values: monthly.map((item) => Number(item.expected)),
                texts: monthly.map((item) => `¥ ${money(item.expected)}`),
              },
              {
                key: "received",
                label: "已收票金额",
                color: "var(--color-chart-1)",
                values: monthly.map((item) => Number(item.received)),
                texts: monthly.map((item) => `¥ ${money(item.received)}`),
              },
            ]}
            line={{
              key: "rate",
              label: "收票／应开比",
              values: monthly.map((item) => (item.percent === null ? null : Number(item.percent))),
              texts: monthly.map((item) => (item.percent === null ? "暂无应开" : `${item.percent}%`)),
            }}
          />
        ) : (
          <EmptyState
            title="近 6 个月暂无可统计的应开或收票金额"
            description="任务应开金额及正常人民币进项发票入库后，将按各自月份展示。"
          />
        )}
        {hasAmounts && (
          <p className="wb-report-note">
            收票金额按发票开票日期统计全部已入库正常人民币进项票（含未匹配），不含红字、已被红冲及作废票。
            应开取任务冻结金额，按关联报关单的 NS 创建月份（北京时间）统计；收票／应开比可超过
            100%，不代表同一批任务完成率。悬停或按 Tab 聚焦月份查看明细。
          </p>
        )}
        {unknown > 0 && (
          <p className="wb-report-note">
            另有 {unknown} 个任务应开金额缺失，未计入应开金额，不影响收票统计。
          </p>
        )}
        {unknownExpectedDates > 0 && (
          <p className="wb-report-note">
            另有 {unknownExpectedDates}{" "}
            个人民币任务未取得关联报关单的创建日期，未计入应开金额趋势；请同步报关单后核对，不影响收票统计。
          </p>
        )}
      </div>
    </section>
  );
}
