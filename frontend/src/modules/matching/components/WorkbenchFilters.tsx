import { useState } from "react";
import { Button, Field, FilterBar } from "../../../shared/components/ui";
import type { WorkbenchQuery } from "../types/workbench";

type Filters = Pick<WorkbenchQuery, "supplierId" | "createdFrom" | "createdTo">;
const EMPTY: Filters = { supplierId: "", createdFrom: "", createdTo: "" };

/** 工作台范围筛选：供应商、报关单创建日期；作用于业务状态分区与核对、开票待办，比对待办不按日期筛选。 */
export function WorkbenchFilters({
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
    <FilterBar
      onSubmit={() => onApply(draft)}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            应用筛选
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
          <span className="wb-filters__hint">比对待办不按报关单日期筛选</span>
        </>
      }
    >
      <Field label="供应商">
        <select value={draft.supplierId} onChange={(event) => set({ supplierId: event.target.value })}>
          <option value="">全部供应商</option>
          {suppliers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="报关单创建日期 从">
        <input
          type="date"
          value={draft.createdFrom}
          onChange={(event) => set({ createdFrom: event.target.value })}
        />
      </Field>
      <Field label="至">
        <input
          type="date"
          value={draft.createdTo}
          onChange={(event) => set({ createdTo: event.target.value })}
        />
      </Field>
    </FilterBar>
  );
}
