import { useState } from "react";
import { Link } from "react-router";
import { taskPath } from "../../../app/paths";
import { Badge, Button, DataTable, type Column } from "../../../shared/components/ui";
import type { BoardNodeKey } from "../types/board";
import type { RecoveryGroup, RecoveryTask, RecoveryView } from "../types/recovery";
import { NODE_TONES } from "./BoardNodeCards";
import { daysText, shortDate, yuan } from "./recovery-format";

// 展开后先显示金额最高的几个任务，其余按需展开，避免长名单撑开页面。
const PREVIEW = 4;

function DaysBadge({ days }: { days: number | null }) {
  if (days == null) return null;
  return (
    <Badge tone={days < 0 ? "danger" : days <= 7 ? "warning" : "neutral"} dot={false}>
      {daysText(days)}
    </Badge>
  );
}

function TaskRows({ group, view }: { group: RecoveryGroup; view: RecoveryView }) {
  const [all, setAll] = useState(false);
  const shown = all ? group.items : group.items.slice(0, PREVIEW);
  const columns: Column<RecoveryTask>[] = [
    { key: "record", header: "CD 号", render: (task) => task.recordNo || "—" },
    { key: "orders", header: "子采购单号", render: (task) => task.orders.join("、") || "—" },
    { key: "expected", header: "应开金额", align: "right", render: (task) => yuan(task.expected) },
    { key: "received", header: "已收", align: "right", render: (task) => yuan(task.received) },
    ...(view === "outstanding" || view === "overdue"
      ? [
          {
            key: "outstanding",
            header: "未收回",
            align: "right" as const,
            render: (task: RecoveryTask) => yuan(task.outstanding),
          },
        ]
      : []),
    { key: "approved", header: "财务审核通过日期", render: (task) => task.approvedOn },
    {
      key: "node",
      header: "当前节点",
      render: (task) => (
        <Badge tone={NODE_TONES[task.node as BoardNodeKey] ?? "neutral"}>{task.nodeLabel}</Badge>
      ),
    },
    {
      key: "action",
      header: <span className="ui-sr-only">操作</span>,
      render: (task) => <Link to={taskPath(task.taskId)}>在开票跟进中查看</Link>,
    },
  ];
  return (
    <div className="rv-tasks">
      <p className="rv-tasks__caption">
        {group.tasks} 个任务{group.tasks > PREVIEW && !all ? ` · 显示金额最高的 ${PREVIEW} 个` : ""}
        {group.unknown ? ` · ${group.unknown} 个应开金额待确认` : ""}
      </p>
      <DataTable
        label={`${group.supplierName}的任务`}
        columns={columns}
        rows={shown}
        rowKey={(task) => task.taskId}
        density="compact"
        minWidth={760}
      />
      {group.items.length > PREVIEW && (
        <Button variant="ghost" size="sm" onClick={() => setAll(!all)}>
          {all ? "只看金额最高的任务" : `显示其余 ${group.items.length - PREVIEW} 个任务`}
        </Button>
      )}
    </div>
  );
}

/** 按供应商 × 采购抬头分组的清单；顺序与金额由后端给出。 */
export function RecoveryTable({
  groups,
  view,
  expanded,
  onToggle,
}: {
  groups: RecoveryGroup[];
  view: RecoveryView;
  expanded: ReadonlySet<string>;
  onToggle: (key: string) => void;
}) {
  const amountHeader = view === "outstanding" || view === "overdue" ? "未收回金额" : "应开金额";
  const columns: Column<RecoveryGroup>[] = [
    {
      key: "toggle",
      header: <span className="ui-sr-only">展开</span>,
      width: "56px",
      render: (group) => (
        <button
          type="button"
          className="rv-toggle"
          aria-expanded={expanded.has(group.key)}
          aria-label={`${expanded.has(group.key) ? "收起" : "展开"}${group.supplierName}明细`}
          onClick={() => onToggle(group.key)}
        >
          {expanded.has(group.key) ? "−" : "+"}
        </button>
      ),
    },
    { key: "supplier", header: "供应商", render: (group) => <strong>{group.supplierName}</strong> },
    {
      key: "member",
      header: "采购员",
      render: (group) =>
        group.memberId === "none" ? <span className="rv-muted">未指定</span> : group.memberName,
    },
    { key: "company", header: "抬头", render: (group) => group.companyName },
    { key: "tasks", header: "任务", align: "right", render: (group) => group.tasks },
    {
      key: "amount",
      header: amountHeader,
      align: "right",
      render: (group) => (
        <strong>
          {yuan(group.amount)}
          {group.unknown ? <span className="rv-muted"> +{group.unknown} 待确认</span> : null}
        </strong>
      ),
    },
    {
      key: "due",
      header: "审核 → 到期",
      render: (group) => (
        <span className="rv-due">
          {shortDate(group.approvedOn)} → {shortDate(group.dueDate)} <DaysBadge days={group.daysLeft} />
        </span>
      ),
    },
  ];
  return (
    <DataTable
      label="回收清单"
      columns={columns}
      rows={groups}
      rowKey={(group) => group.key}
      minWidth={900}
      rowTone={(group) => (expanded.has(group.key) ? "accent" : undefined)}
      renderDetails={(group) => (expanded.has(group.key) ? <TaskRows group={group} view={view} /> : null)}
    />
  );
}
