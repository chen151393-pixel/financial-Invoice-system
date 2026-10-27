import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { DonutChart, TrendChart } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Workbench } from "../types/workbench";

/**
 * 应开与已收：按任务生成月份汇总人民币应开（折线）与目前已收票（柱），金额与收票率来自后端；
 * 图形只用金额画图，悬停文字为后端十进制字符串。
 */
export function WorkbenchReceipts({ monthly }: { monthly: Workbench["monthly"] }) {
  const unknown = monthly.reduce((sum, item) => sum + item.unknownTasks, 0);
  return (
    <section className="wb-panel" aria-labelledby="wb-receipts-title">
      <div className="wb-panel__head">
        <h2 id="wb-receipts-title">
          应开与已收票金额
          <small>按任务生成月份 · 人民币</small>
        </h2>
      </div>
      <div className="wb-panel__body">
        <TrendChart
          label="按任务生成月份的应开与已收票金额"
          height={220}
          categories={monthly.map((item) => `${Number(item.month.slice(5))}月`)}
          bars={[
            {
              key: "received",
              label: "已收票",
              values: monthly.map((item) => Number(item.received)),
              texts: monthly.map(
                (item) =>
                  `¥ ${money(item.received)}${item.percent === null ? "" : `（收票率 ${item.percent}%）`}`,
              ),
            },
          ]}
          line={{
            key: "expected",
            label: "应开",
            values: monthly.map((item) => Number(item.expected)),
            texts: monthly.map((item) => `¥ ${money(item.expected)}`),
          }}
        />
        {unknown > 0 && <p className="wb-report-note">另有 {unknown} 个任务应开金额缺失，未计入。</p>}
      </div>
    </section>
  );
}

/** 比对队列：待审核建议按置信度分档（后端计数），点击进入比对审核队列。 */
export function WorkbenchQueueTiers({ queue }: { queue: NonNullable<Workbench["queue"]> }) {
  return (
    <section className="wb-panel" aria-labelledby="wb-queue-title">
      <div className="wb-panel__head">
        <h2 id="wb-queue-title">发票比对队列</h2>
        <Link to={paths.matching}>去审核 →</Link>
      </div>
      <div className="wb-panel__body">
        <DonutChart
          label="待审核比对建议按置信度分布"
          size={140}
          centerLabel="条待审核"
          centerValue={String(queue.all)}
          segments={[
            { key: "high", label: "高置信度", value: queue.high, text: String(queue.high) },
            { key: "medium", label: "中置信度", value: queue.medium, text: String(queue.medium) },
            { key: "low", label: "低置信度", value: queue.low, text: String(queue.low) },
          ]}
        />
        <p className="wb-report-note">高置信度且比对项全部一致的建议可在队列中批量通过。</p>
      </div>
    </section>
  );
}
