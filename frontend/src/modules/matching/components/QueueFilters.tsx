import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { QueueQuery } from "../types/matching";

type Filters = Pick<QueueQuery, "supplierId" | "invoiceFrom" | "invoiceTo">;
const EMPTY: Filters = { supplierId: "", invoiceFrom: "", invoiceTo: "" };

/** 比对队列筛选：子采购单供应商、开票日期（起止须同时填写，由后端校验）。 */
export function QueueFilters({
  value,
  suppliers,
  busy,
  onApply,
}: {
  value: Filters;
  suppliers: { id: string; name: string }[];
  busy: boolean;
  onApply: (filters: Filters) => void;
}) {
  const [draft, setDraft] = useState<Filters>(value);
  const set = (patch: Partial<Filters>) => setDraft((current) => ({ ...current, ...patch }));
  return (
    <form
      className="matching-filters"
      onSubmit={(event) => {
        event.preventDefault();
        onApply(draft);
      }}
    >
      <label>
        供应商
        <select value={draft.supplierId} onChange={(event) => set({ supplierId: event.target.value })}>
          <option value="">全部供应商</option>
          {suppliers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        开票日期 从
        <input
          type="date"
          value={draft.invoiceFrom}
          onChange={(event) => set({ invoiceFrom: event.target.value })}
        />
      </label>
      <label>
        至
        <input
          type="date"
          value={draft.invoiceTo}
          onChange={(event) => set({ invoiceTo: event.target.value })}
        />
      </label>
      <Button type="submit" variant="primary" disabled={busy}>
        查询
      </Button>
      <Button
        disabled={busy}
        onClick={() => {
          setDraft(EMPTY);
          onApply(EMPTY);
        }}
      >
        清除
      </Button>
    </form>
  );
}
