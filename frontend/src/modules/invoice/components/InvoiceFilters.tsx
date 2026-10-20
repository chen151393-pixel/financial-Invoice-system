import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { InvoiceAccountOption, InvoiceFilters as Filters } from "../types/invoice";
import "./invoice-status.css";

export const emptyFilters: Filters = { q: "", account: "", status: "", date_from: "", date_to: "" };

export function InvoiceFilters({
  draft,
  applied,
  accounts,
  loading,
  onChange,
  onSubmit,
  onReset,
  onRefresh,
}: {
  draft: Filters;
  applied?: Filters;
  accounts?: { items: InvoiceAccountOption[]; loading: boolean; error: string };
  loading: boolean;
  onChange: (draft: Filters) => void;
  onSubmit: () => void;
  onReset: () => void;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const pending =
    applied && (Object.keys(emptyFilters) as (keyof Filters)[]).some((key) => draft[key] !== applied[key]);
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
        <label className="invoice-list__account-filter">
          账套
          <select
            value={draft.account}
            disabled={accounts?.loading || (!accounts?.items.length && !!accounts?.error)}
            onChange={(event) => onChange({ ...draft, account: event.target.value })}
          >
            <option value="">{accounts?.loading ? "正在读取账套…" : "全部账套"}</option>
            {accounts?.items.map((account) => (
              <option key={account.value} value={account.value}>
                {account.label}
              </option>
            ))}
          </select>
        </label>
        <label className="invoice-list__status-filter">
          票面状态
          <select
            value={draft.status}
            onChange={(event) => onChange({ ...draft, status: event.target.value })}
          >
            <option value="">全部状态</option>
            <option value="normal">正常</option>
            <option value="red_letter">红字发票</option>
            <option value="red_offset">已被红冲</option>
            <option value="void">作废</option>
            <option value="unknown">未知</option>
          </select>
        </label>
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
      {accounts?.error && (
        <p role="alert" className="invoice-list__error">
          {accounts.error}，可点击“刷新数据”重试。
        </p>
      )}
      {pending && <p role="status">筛选条件已修改，请点击“查询”应用；当前结果仍对应上次查询。</p>}
      {expanded && (
        <div className="invoice-list__more-filters" id="invoice-more-filters">
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
