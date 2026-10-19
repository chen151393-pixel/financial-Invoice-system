import { useId, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { TaskListQuery } from "../types/task";
import "./task-list-toolbar.css";

type Filter = "keyword" | "account" | "status";
type Props = {
  query: TaskListQuery;
  busy: boolean;
  onChange: (patch: Partial<TaskListQuery>) => void;
  onClear: (filter: Filter | "all") => void;
};

export function TaskListToolbar({ query, busy, onChange, onClear }: Props) {
  const [showHelp, setShowHelp] = useState(false);
  const helpId = useId();
  const actions = useRef<HTMLDivElement>(null);
  const filters: { key: Filter; label: string }[] = [];
  if (query.keyword) filters.push({ key: "keyword", label: `关键词：${query.keyword}` });
  if (query.account) filters.push({ key: "account", label: `NS 环境：${query.account}` });
  if (query.status !== "current") {
    filters.push({ key: "status", label: `任务版本：${query.status === "all" ? "全部版本" : "已被替代"}` });
  }
  function clear(filter: Filter | "all") {
    // 清除后标签会消失，将键盘焦点交回稳定的工具栏入口。
    actions.current?.querySelector<HTMLButtonElement>("button")?.focus();
    onClear(filter);
  }
  return (
    <div className="task-list-toolbar">
      <div className="task-list-toolbar__row">
        <div className="task-list-toolbar__switch" role="group" aria-label="任务分组方式">
          <Button
            aria-pressed={query.groupBy === "supplier"}
            disabled={busy}
            onClick={() => onChange({ groupBy: "supplier" })}
          >
            按供应商
          </Button>
          <Button
            aria-pressed={query.groupBy === "declaration"}
            disabled={busy}
            onClick={() => onChange({ groupBy: "declaration" })}
          >
            按报关单
          </Button>
        </div>
        <div className="task-list-toolbar__actions" ref={actions}>
          <label>
            任务版本
            <select
              value={query.status}
              disabled={busy}
              onChange={(event) => onChange({ status: event.target.value as TaskListQuery["status"] })}
            >
              <option value="current">当前任务</option>
              <option value="superseded">已被替代</option>
              <option value="all">全部版本</option>
            </select>
          </label>
          <Button
            className="task-list-toolbar__help"
            aria-expanded={showHelp}
            aria-controls={helpId}
            onClick={() => setShowHelp((value) => !value)}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 10v7M12 7v1" />
            </svg>
            口径说明
          </Button>
        </div>
      </div>
      <div id={helpId} hidden={!showHelp} className="task-list-toolbar__explanation">
        <p>
          财务审核通过后按供应商、采购公司和币种生成任务，合同归档到共享盘。通知支持提交企微群发并等待群主确认，也可登记人工发送；收票进度由发票比对确认自动汇总。
        </p>
        <p>
          每行一个开票任务，按所选分组顺序平铺并按完整分组分页；首列随分组方式显示供应商或报关单号。待开票包含待保存合同、待通知供应商、等待开票和部分收票的任务，待处理与待开票可重叠。
        </p>
        <p>
          收票金额进度来自已通过比对的有效分配，不代表任务已完成。最近联系取已登记或企微确认的发送时间，经办人为该次通知的发送员工。
        </p>
        <p>等待天数从任务创建起算，完成或被替代后停止展示天数。</p>
      </div>
      {filters.length > 0 && (
        <div className="task-list-toolbar__filters" role="group" aria-label="已应用的筛选条件">
          {filters.map((filter) => (
            <Button
              key={filter.key}
              className="task-list-toolbar__chip"
              disabled={busy}
              aria-label={`清除${filter.label}`}
              onClick={() => clear(filter.key)}
            >
              <span>{filter.label}</span>
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <path d="m3 3 6 6m0-6-6 6" />
              </svg>
            </Button>
          ))}
          <Button className="task-list-toolbar__clear" disabled={busy} onClick={() => clear("all")}>
            清空筛选
          </Button>
        </div>
      )}
    </div>
  );
}
