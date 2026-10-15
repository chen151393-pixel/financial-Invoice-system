import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { InvoiceFilters as Filters } from "../types/invoice";

export const emptyFilters: Filters = { q: "", status: "", date_from: "", date_to: "" };

export function InvoiceFilters({
  draft,
  loading,
  onChange,
  onSubmit,
  onReset,
  onRefresh,
}: {
  draft: Filters;
  loading: boolean;
  onChange: (draft: Filters) => void;
  onSubmit: () => void;
  onReset: () => void;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <form
      className="invoice-list__filters"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="invoice-list__toolbar">
        <input
          aria-label="搜索发票号码、供应商或税号"
          value={draft.q}
          maxLength={100}
          placeholder="搜索发票 / 供应商 / 税号"
          onChange={(event) => onChange({ ...draft, q: event.target.value })}
        />
        <Button type="submit" disabled={loading}>
          查询
        </Button>
        <div className="invoice-list__tools">
          <Button
            aria-expanded={expanded}
            aria-controls="invoice-more-filters"
            onClick={() => setExpanded(!expanded)}
          >
            更多筛选
          </Button>
          <Button disabled={loading} onClick={onRefresh}>
            刷新数据
          </Button>
        </div>
      </div>
      {expanded && (
        <div className="invoice-list__more-filters" id="invoice-more-filters">
          <label>
            票面状态
            <select
              value={draft.status}
              onChange={(event) => onChange({ ...draft, status: event.target.value })}
            >
              <option value="">全部状态</option>
              <option value="normal">正常</option>
              <option value="red_offset">已红冲</option>
              <option value="void">作废</option>
              <option value="unknown">未知</option>
            </select>
          </label>
          <label>
            开票日期从
            <input
              type="date"
              value={draft.date_from}
              onChange={(event) => onChange({ ...draft, date_from: event.target.value })}
            />
          </label>
          <label>
            至
            <input
              type="date"
              value={draft.date_to}
              onChange={(event) => onChange({ ...draft, date_to: event.target.value })}
            />
          </label>
          <Button type="submit" disabled={loading}>
            应用筛选
          </Button>
          <Button disabled={loading} onClick={onReset}>
            重置
          </Button>
        </div>
      )}
    </form>
  );
}
