import { Link } from "react-router";
import { matchingQueuePath } from "../../../app/paths";
import { Progress } from "../../../shared/components/ui";
import type { Workbench } from "../types/workbench";

const TIERS = [
  ["high", "高置信度"],
  ["medium", "中置信度"],
  ["low", "低置信度"],
] as const;

/**
 * 发票比对队列：待审核建议按置信度分档（堆叠条只按后端计数画宽度）与比对项不一致的分类计数，
 * 高置信度建议链接到队列的高置信度分档批量处理。
 */
export function WorkbenchQueue({ queue }: { queue: NonNullable<Workbench["queue"]> }) {
  return (
    <section className="wb-panel" aria-labelledby="wb-queue-title">
      <div className="wb-panel__head">
        <div>
          <h2 id="wb-queue-title">发票比对队列</h2>
          <p className="wb-panel__sub">待审核比对建议 {queue.all} 条 · 按置信度与异常类型</p>
        </div>
      </div>
      <div className="wb-panel__body wb-queue">
        <div
          className="wb-queue__bar"
          role="img"
          aria-label={TIERS.map(([key, label]) => `${label} ${queue[key]} 条`).join("，")}
        >
          {queue.all > 0 &&
            TIERS.map(([key]) => <span key={key} data-tier={key} style={{ flexGrow: queue[key] }} />)}
        </div>
        <ul className="wb-queue__legend">
          {TIERS.map(([key, label]) => (
            <li key={key}>
              <i data-tier={key} />
              {label} <strong>{queue[key]}</strong>
            </li>
          ))}
        </ul>
        <h3>比对项不一致</h3>
        {queue.anomalies.length ? (
          <ul className="wb-queue__anomalies">
            {queue.anomalies.map((item) => (
              <li key={item.label}>
                <span>{item.label}不一致</span>
                <Progress
                  width={item.percent}
                  label={`${item.label}不一致 ${item.count} 条`}
                  tone="warning"
                />
                <strong>{item.count}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="wb-report-note wb-queue__empty">待审核建议的比对项全部一致。</p>
        )}
        {queue.high > 0 ? (
          <Link className="wb-queue__action" to={matchingQueuePath({ tier: "high" })}>
            高置信度 {queue.high} 条，去队列批量通过 →
          </Link>
        ) : (
          <Link className="wb-queue__action" to={matchingQueuePath({})}>
            去比对审核队列 →
          </Link>
        )}
      </div>
    </section>
  );
}
