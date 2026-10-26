import { Alert, Button, Field, FilterBar } from "../../../shared/components/ui";
import type { InvoiceAccountOption, InvoiceFilters as Filters } from "../types/invoice";
import "./invoice-status.css";

export const emptyFilters: Filters = { q: "", account: "", status: "", date_from: "", date_to: "" };

/** 发票查询条件：关键字、账套、票面状态与开票日期一行展示，查询按钮紧跟条件。 */
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
  const pending =
    applied && (Object.keys(emptyFilters) as (keyof Filters)[]).some((key) => draft[key] !== applied[key]);
  return (
    <>
      <FilterBar
        onSubmit={onSubmit}
        pending={pending ? "筛选条件已修改，请点击“查询”应用；当前结果仍对应上次查询。" : undefined}
        actions={
          <>
            <Button type="submit" variant="primary" disabled={loading}>
              查询
            </Button>
            <Button disabled={loading} onClick={onReset}>
              重置
            </Button>
            <Button disabled={loading} onClick={onRefresh}>
              刷新数据
            </Button>
          </>
        }
      >
        <Field label="发票 / 供应商 / 税号" grow>
          <input
            value={draft.q}
            maxLength={100}
            placeholder="搜索发票号码、供应商或税号"
            onChange={(event) => onChange({ ...draft, q: event.target.value })}
          />
        </Field>
        <Field label="账套">
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
        </Field>
        <Field label="票面状态">
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
        </Field>
        <Field label="开票日期 从">
          <input
            type="date"
            value={draft.date_from}
            onChange={(event) => onChange({ ...draft, date_from: event.target.value })}
          />
        </Field>
        <Field label="至">
          <input
            type="date"
            value={draft.date_to}
            onChange={(event) => onChange({ ...draft, date_to: event.target.value })}
          />
        </Field>
      </FilterBar>
      {accounts?.error && <Alert tone="danger">{accounts.error}，可点击“刷新数据”重试。</Alert>}
    </>
  );
}
