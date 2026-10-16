import { useId, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { PlSearchCriteria } from "../types";
import "./pl-search-form.css";

export type { PlSearchCriteria } from "../types";
const initial: PlSearchCriteria = {
  type: "customsRecord",
  pl: "",
  month: "",
  createdFrom: "",
  createdTo: "",
  showIncomplete: true,
};
const queryTypes = [
  { value: "pl", label: "PL单号" },
  { value: "customsRecord", label: "NS报关记录号（CD编号）" },
  { value: "declaration", label: "真实报关单号" },
] as const;

export function PlSearchForm({
  onSearch,
  onReset,
  busy = false,
  submitLabel,
}: {
  onSearch: (criteria: PlSearchCriteria) => void;
  onReset: () => void;
  busy?: boolean;
  submitLabel: string;
}) {
  const id = useId();
  const [criteria, setCriteria] = useState<PlSearchCriteria>(initial);
  return (
    <form
      className="pl-search-form"
      role="search"
      aria-label="采购报关查询条件"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy) onSearch(criteria);
      }}
      onReset={() => {
        setCriteria(initial);
        onReset();
      }}
    >
      <h2>查找报关与采购单据</h2>
      <div className="pl-search-form__primary">
        <label>
          查询方式
          <select
            value={criteria.type}
            disabled={busy}
            onChange={(event) => {
              const type = queryTypes.find((item) => item.value === event.target.value)?.value;
              if (type) setCriteria({ ...criteria, type });
            }}
          >
            {queryTypes.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="pl-search-form__number">
          查询单号
          <input
            value={criteria.pl}
            disabled={busy}
            placeholder={criteria.type === "customsRecord" ? "例如 CD000630" : "输入完整单号"}
            autoComplete="off"
            onChange={(event) => setCriteria({ ...criteria, pl: event.target.value })}
          />
        </label>
        <div className="pl-search-form__actions">
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "查询中…" : submitLabel}
          </Button>
          <Button type="reset">清空</Button>
        </div>
      </div>
      <details className="pl-search-form__advanced">
        <summary>
          更多查询条件
          {(criteria.month || criteria.createdFrom || criteria.createdTo || !criteria.showIncomplete) && (
            <span>（已设置）</span>
          )}
        </summary>
        <div className="pl-search-form__dates">
          <label>
            申报月份
            <input
              type="month"
              value={criteria.month}
              disabled={busy}
              aria-describedby={id + "-hint"}
              onChange={(event) => setCriteria({ ...criteria, month: event.target.value })}
            />
          </label>
          <label>
            创建日期 · 起始
            <input
              type="date"
              value={criteria.createdFrom}
              disabled={busy}
              aria-describedby={id + "-hint"}
              onChange={(event) => setCriteria({ ...criteria, createdFrom: event.target.value })}
            />
          </label>
          <label>
            创建日期 · 结束
            <input
              type="date"
              value={criteria.createdTo}
              disabled={busy}
              aria-describedby={id + "-hint"}
              onChange={(event) => setCriteria({ ...criteria, createdTo: event.target.value })}
            />
          </label>
        </div>
        <label className="pl-search-form__option">
          <input
            type="checkbox"
            checked={criteria.showIncomplete}
            disabled={busy}
            onChange={(event) => setCriteria({ ...criteria, showIncomplete: event.target.checked })}
          />
          显示无真实报关单号且无子采购单的报关单
        </label>
        <p id={id + "-hint"}>
          单号、申报月份或完整创建日期范围至少填写一项。创建日期包含结束当天；多个条件同时生效。
        </p>
      </details>
    </form>
  );
}
