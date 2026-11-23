import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { RecoveryBoard, RecoveryView } from "../types/recovery";
import { daysText, percent, unknownNote, yuan } from "./recovery-format";

/** 四张概况卡同时是清单切换入口；数字均为后端按当前筛选给出的结果。 */
export function RecoveryStats({
  board,
  view,
  disabled,
  onSelect,
}: {
  board: RecoveryBoard;
  view: RecoveryView;
  disabled: boolean;
  onSelect: (view: RecoveryView) => void;
}) {
  const { due, collected, outstanding, overdue } = board.cards;
  const prefix = board.month === "all" ? "全部" : board.monthLabel;
  const left = daysText(outstanding.daysLeft);
  const months = overdue.months.length ? ` · ${overdue.months.join("、")}通知` : "";
  return (
    <StatGrid label="按回收情况切换下方清单" min={240}>
      <StatCard
        glyph="应"
        tone="primary"
        label={`${prefix}应收回`}
        value={`${due.tasks} 个`}
        note={`${yuan(due.amount)} · ${due.suppliers} 家供应商${unknownNote(due)}`}
        selected={view === "due"}
        disabled={disabled}
        onSelect={() => onSelect("due")}
      />
      <StatCard
        glyph="收"
        label={`${prefix}已收回`}
        value={
          <>
            {collected.tasks} 个 <span className="rv-rate">{percent(collected.rate)}</span>
          </>
        }
        note={
          <span className="rv-meter-note">
            <span className="rv-meter" role="img" aria-label={`回收率 ${percent(collected.rate)}`}>
              <span style={{ width: `${Math.min(100, collected.rate ?? 0)}%` }} />
            </span>
            {yuan(collected.amount)}
          </span>
        }
        selected={view === "collected"}
        disabled={disabled}
        onSelect={() => onSelect("collected")}
      />
      <StatCard
        glyph="未"
        tone={outstanding.tasks ? "warning" : "neutral"}
        label={`${prefix}未收回`}
        value={`${outstanding.tasks} 个`}
        note={`${yuan(outstanding.amount)} · ${outstanding.suppliers} 家${left ? ` · ${left}` : ""}${unknownNote(outstanding)}`}
        selected={view === "outstanding"}
        disabled={disabled}
        onSelect={() => onSelect("outstanding")}
      />
      <StatCard
        glyph="逾"
        tone={overdue.tasks ? "warning" : "neutral"}
        label={`逾期未收回${months}`}
        value={`${overdue.tasks} 个`}
        note={`${yuan(overdue.amount)} · ${overdue.suppliers} 家 · 超 30 天 ${overdue.longOverdue} 个${unknownNote(overdue)}`}
        selected={view === "overdue"}
        disabled={disabled}
        onSelect={() => onSelect("overdue")}
      />
    </StatGrid>
  );
}
