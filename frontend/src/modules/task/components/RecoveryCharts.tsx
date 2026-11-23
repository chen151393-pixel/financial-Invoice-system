import type { ReactNode } from "react";
import type { RecoveryBoard, RecoveryMonth } from "../types/recovery";
import { percent, wan, yuan } from "./recovery-format";

// 回收率低于该值的采购员用警示色；只影响颜色，不改变排序或口径。
const LOW_RATE = 80;
const PALETTE = [
  "var(--color-chart-line)",
  "var(--color-chart-1)",
  "var(--color-chart-4)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
];
const REST = "var(--color-chart-5)";

function ChartCard({
  title,
  description,
  footer,
  children,
}: {
  title: string;
  description: string;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rv-chart">
      <header className="rv-chart__head">
        <h3>{title}</h3>
        <p title={description}>{description}</p>
      </header>
      <div className="rv-chart__body">{children}</div>
      <footer className="rv-chart__foot">{footer}</footer>
    </section>
  );
}

const Key = ({ color, children }: { color: string; children: ReactNode }) => (
  <span className="rv-key">
    <i style={{ background: color }} aria-hidden="true" />
    {children}
  </span>
);

function MonthBars({ months }: { months: RecoveryMonth[] }) {
  const highest = Math.max(1, ...months.map((item) => Number(item.expected)));
  const summary = months
    .map((item) => `${item.label}通知 ${item.tasks} 个，回收率 ${percent(item.rate)}`)
    .join("；");
  return (
    <>
      <div className="rv-columns" role="img" aria-label={summary}>
        {months.map((item) => {
          const done = (Number(item.collectedAmount) / highest) * 100;
          const rest = (Number(item.outstandingAmount) / highest) * 100;
          return (
            <div key={item.month} className="rv-columns__item" data-state={item.state}>
              <strong data-low={item.rate !== null && item.rate < LOW_RATE ? "" : undefined}>
                {item.tasks ? percent(item.rate) : "—"}
              </strong>
              <div className="rv-columns__bar">
                <span className="rv-columns__rest" style={{ height: `${rest}%` }} />
                <span className="rv-columns__done" style={{ height: `${done}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="rv-columns__labels">
        {months.map((item) => (
          <div key={item.month}>
            <b>{item.label}</b>
            <span>
              {item.state === "open" ? "回收中" : `${item.dueDate.slice(5).replace("-", "/")} 到期`}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

/** 回收概况三张图：卡片同高，标题一行、图区固定高度、底部汇总栏对齐。 */
export function RecoveryCharts({
  board,
  activeMember,
  onBuyer,
}: {
  board: RecoveryBoard;
  activeMember: string;
  onBuyer: (memberId: string) => void;
}) {
  const share = board.concentration;
  const due = board.cards.due;
  return (
    <div className="rv-charts">
      <ChartCard
        title="按通知月份回收"
        description="柱高为应开金额，顶部为按任务数的回收率"
        footer={
          <>
            <Key color="var(--color-chart-1)">已收回</Key>
            <Key color="var(--color-warning)">未收回</Key>
            <span className="rv-chart__aside">已到期月份平均 {percent(board.recentRate)}</span>
          </>
        }
      >
        <MonthBars months={board.months} />
      </ChartCard>
      <ChartCard
        title="按采购员回收率"
        description="按任务数计，点击姓名即按采购员筛选"
        footer={
          <>
            <Key color="var(--color-chart-1)">≥ {LOW_RATE}%</Key>
            <Key color="var(--color-warning)">低于 {LOW_RATE}%</Key>
            <span className="rv-chart__aside">
              应收回 {due.tasks} · 未收回 {board.cards.outstanding.tasks}
            </span>
          </>
        }
      >
        {board.buyers.length ? (
          <ul className="rv-buyers">
            {board.buyers.map((buyer) => {
              const low = buyer.rate !== null && buyer.rate < LOW_RATE;
              return (
                <li key={buyer.memberId}>
                  <span className="rv-buyers__name">
                    <button
                      type="button"
                      aria-pressed={activeMember === buyer.memberId}
                      onClick={() => onBuyer(activeMember === buyer.memberId ? "" : buyer.memberId)}
                    >
                      {buyer.name}
                    </button>
                    <span data-low={buyer.outstanding && low ? "" : undefined}>
                      未收回 {buyer.outstanding} 个
                    </span>
                  </span>
                  <span className="rv-buyers__track" aria-hidden="true">
                    <span
                      style={{
                        width: `${buyer.rate ?? 0}%`,
                        background: low ? "var(--color-warning)" : "var(--color-chart-1)",
                      }}
                    />
                  </span>
                  <strong data-low={low ? "" : undefined}>{percent(buyer.rate)}</strong>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="rv-chart__empty">当前条件下没有应收回任务</p>
        )}
        <div className="rv-buyers__axis" aria-hidden="true">
          <span className="rv-buyers__ticks">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </span>
        </div>
      </ChartCard>
      <ChartCard
        title="未收回金额集中度"
        description="当前条件下未收回金额按供应商占比"
        footer={
          <>
            <span>
              前 {share.top.length} 家合计{" "}
              <strong>
                {wan(share.topAmount)} · {percent(share.topShare)}
              </strong>
            </span>
            <span className="rv-chart__aside">共 {share.suppliers} 家</span>
          </>
        }
      >
        {share.suppliers ? (
          <Donut board={board} />
        ) : (
          <p className="rv-chart__empty">当前条件下没有未收回金额</p>
        )}
      </ChartCard>
    </div>
  );
}

function Donut({ board }: { board: RecoveryBoard }) {
  const share = board.concentration;
  const items = [
    ...share.top.map((item, index) => ({ ...item, key: String(item.supplierId), color: PALETTE[index] })),
    ...(share.restSuppliers
      ? [
          {
            key: "rest",
            name: `其余 ${share.restSuppliers} 家`,
            amount: share.restAmount,
            share: share.restShare,
            color: REST,
          },
        ]
      : []),
  ];
  const size = 136;
  const stroke = 22;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <figure
      className="rv-donut"
      aria-label={`未收回金额按供应商占比：前 ${share.top.length} 家合计 ${percent(share.topShare)}`}
    >
      <div className="rv-donut__ring">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-canvas)"
            strokeWidth={stroke}
          />
          {items.map((item) => {
            const length = ((item.share ?? 0) / 100) * circumference;
            const arc = (
              <circle
                key={item.key}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={item.color}
                strokeWidth={stroke}
                strokeDasharray={`${Math.max(0, length - 1.5)} ${circumference}`}
                strokeDashoffset={-offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
              />
            );
            offset += length;
            return arc;
          })}
        </svg>
        <span className="rv-donut__center">
          未收回
          <strong>{wan(share.amount)}</strong>
        </span>
      </div>
      <ul className="rv-donut__legend">
        {items.map((item) => (
          <li key={item.key} title={`${item.name} ${yuan(item.amount)}`}>
            <i style={{ background: item.color }} aria-hidden="true" />
            <span>{item.name}</span>
            <strong>{percent(item.share)}</strong>
          </li>
        ))}
      </ul>
    </figure>
  );
}
