import { TrendChart } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Workbench } from "../types/workbench";

/**
 * 应开与已收票金额趋势：按任务生成月份的人民币应开（浅柱）、目前已收票（深柱）与收票率（折线，右轴），
 * 金额与收票率来自后端；图形只用金额画图，悬停和点上文字为后端十进制字符串。
 */
export function WorkbenchReceipts({ monthly }: { monthly: Workbench["monthly"] }) {
  const unknown = monthly.reduce((sum, item) => sum + item.unknownTasks, 0);
  return (
    <section className="wb-panel" aria-labelledby="wb-receipts-title">
      <div className="wb-panel__head">
        <div>
          <h2 id="wb-receipts-title">应开与已收票金额趋势</h2>
          <p className="wb-panel__sub">按开票任务生成月份 · 人民币 · 折线为收票率</p>
        </div>
      </div>
      <div className="wb-panel__body">
        <TrendChart
          label="按任务生成月份的应开、已收票金额与收票率"
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
            label: "收票率",
            values: monthly.map((item) => Number(item.percent ?? 0)),
            texts: monthly.map((item) => (item.percent === null ? "—" : `${item.percent}%`)),
          }}
        />
        {unknown > 0 && <p className="wb-report-note">另有 {unknown} 个任务应开金额缺失，未计入。</p>}
      </div>
    </section>
  );
}
