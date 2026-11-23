import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Pagination,
  SectionTitle,
  Skeleton,
} from "../../../shared/components/ui";
import { RecoveryCharts } from "../components/RecoveryCharts";
import { RecoverySearch } from "../components/RecoverySearch";
import { RecoveryStats } from "../components/RecoveryStats";
import { RecoveryTable } from "../components/RecoveryTable";
import { daysText, shortDate, unknownNote, yuan } from "../components/recovery-format";
import { useRecoveryBoard } from "../hooks/useRecoveryBoard";
import type { RecoveryBoard, RecoveryView } from "../types/recovery";
import "./recovery-board.css";

const VIEW_TITLES: Record<RecoveryView, string> = {
  due: "应收回",
  collected: "已收回",
  outstanding: "未收回",
  overdue: "逾期未收回",
};
const PAGE_SIZES = [10, 20, 50] as const;

function listTitle(board: RecoveryBoard) {
  const view = board.list.view;
  if (view === "overdue") return VIEW_TITLES.overdue;
  return `${board.month === "all" ? "全部月份" : board.monthLabel}${VIEW_TITLES[view]}`;
}

/** 应收看板：只读审计页，处理任务在开票跟进中进行。 */
export function RecoveryBoardPage() {
  const { state, query, search, reload, download, exporting, exportNotice } = useRecoveryBoard();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const board = state.data;
  const busy = state.kind === "loading";
  if (!board) {
    return state.kind === "error" ? (
      <ErrorState
        title="应收看板读取失败"
        message={state.message}
        action={<Button onClick={reload}>重试</Button>}
      />
    ) : (
      <Skeleton rows={6} label="正在读取应收看板" />
    );
  }
  const list = board.list;
  const amountLabel = list.view === "outstanding" || list.view === "overdue" ? "未收回" : "应开";
  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  const allOpen = list.items.length > 0 && list.items.every((group) => expanded.has(group.key));
  return (
    <div className="rv-page" aria-busy={busy}>
      {state.kind === "error" && (
        <Alert tone="danger" title="刷新失败，仍显示上次结果">
          {state.message}
        </Alert>
      )}
      <RecoveryStats
        board={board}
        view={query.view}
        disabled={busy}
        onSelect={(view) => search({ ...query, view, page: 1 })}
      />
      <RecoverySearch board={board} query={query} busy={busy} onSearch={search} onRefresh={reload} />

      <SectionTitle
        title="回收概况"
        count={
          board.dueDate
            ? `${board.monthLabel} · ${shortDate(board.dueDate).replace("-", "/")} 到期`
            : "全部月份"
        }
      />
      <RecoveryCharts
        board={board}
        activeMember={query.memberId}
        onBuyer={(memberId) => search({ ...query, memberId, page: 1 })}
      />

      <SectionTitle title="回收清单" count="随上方卡片切换" />
      <Card className="rv-list">
        <CardHeader
          title={
            <span className="rv-list__title">
              {listTitle(board)}
              {list.view !== "overdue" && board.dueDate && (
                <Badge tone={list.view === "collected" ? "success" : "warning"}>
                  {shortDate(board.dueDate).replace("-", "/")} 到期
                  {list.view === "outstanding" && board.cards.outstanding.daysLeft !== null
                    ? ` · ${daysText(board.cards.outstanding.daysLeft)}`
                    : ""}
                </Badge>
              )}
            </span>
          }
          description={`${list.summary.suppliers} 家供应商 · ${list.summary.tasks} 个任务 · ${amountLabel} ${yuan(list.summary.amount)}${unknownNote(list.summary)} · 部分收票的任务按未收部分计 · 金额高的在前`}
          actions={
            <>
              <Button
                variant="ghost"
                disabled={!list.items.length}
                onClick={() =>
                  setExpanded(allOpen ? new Set() : new Set(list.items.map((group) => group.key)))
                }
              >
                {allOpen ? "收起全部" : "展开全部"}
              </Button>
              <Button disabled={exporting || !list.total} onClick={() => void download()}>
                {exporting ? "导出中…" : "导出清单"}
              </Button>
            </>
          }
        />
        {exportNotice && (
          <p className="rv-list__notice" role="status">
            {exportNotice}
          </p>
        )}
        {list.items.length ? (
          <RecoveryTable groups={list.items} view={list.view} expanded={expanded} onToggle={toggle} />
        ) : (
          <EmptyState
            title={`没有${VIEW_TITLES[list.view]}的任务`}
            description="可切换通知月份或上方卡片，或清除筛选条件后再看"
          />
        )}
        {list.total > 0 && (
          <div className="rv-list__pages">
            <Pagination
              label="回收清单分页"
              total={list.total}
              unit="家供应商"
              page={list.page}
              pageCount={list.pages}
              pageSize={list.pageSize}
              pageSizes={PAGE_SIZES}
              disabled={busy}
              onPageChange={(page) => search({ ...query, page })}
              onPageSizeChange={(pageSize) => search({ ...query, pageSize, page: 1 })}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
