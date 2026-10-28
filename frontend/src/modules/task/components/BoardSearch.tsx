import { useState } from "react";
import { Button, Field, FilterBar } from "../../../shared/components/ui";

export interface BoardSearchValues {
  supplierName: string;
  recordNo: string;
  purchaseOrderNo: string;
}

function sameSearch(left: BoardSearchValues, right: BoardSearchValues) {
  return (
    left.supplierName === right.supplierName &&
    left.recordNo === right.recordNo &&
    left.purchaseOrderNo === right.purchaseOrderNo
  );
}

export function BoardSearch({
  values,
  busy,
  filtered,
  onSearch,
  onClear,
  onRefresh,
}: {
  values: BoardSearchValues;
  busy: boolean;
  filtered: boolean;
  onSearch: (values: BoardSearchValues) => void;
  onClear: () => void;
  onRefresh: () => void;
}) {
  const [draft, setDraft] = useState(values);
  const [applied, setApplied] = useState(values);
  // 地址恢复或清除条件时同步输入值，保持输入框和按钮挂载，避免查询后丢失键盘焦点。
  if (!sameSearch(applied, values)) {
    setApplied(values);
    setDraft(values);
  }
  const edited = !sameSearch(draft, values);
  return (
    <FilterBar
      embedded
      onSubmit={() => {
        if (!busy) onSearch(draft);
      }}
      pending={edited ? "条件已修改，点击「查询」生效；多个条件同时满足" : undefined}
      actions={
        <>
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? "查询中…" : "查询"}
          </Button>
          <Button
            disabled={busy || (!filtered && !Object.values(draft).some(Boolean))}
            onClick={() => {
              setDraft({ supplierName: "", recordNo: "", purchaseOrderNo: "" });
              onClear();
            }}
          >
            清除
          </Button>
          <Button disabled={busy} onClick={onRefresh}>
            刷新
          </Button>
        </>
      }
    >
      <Field label="供应商" grow hideLabel>
        <input
          type="search"
          name="supplierName"
          placeholder="输入供应商名称或关键词"
          value={draft.supplierName}
          onChange={(event) => setDraft({ ...draft, supplierName: event.target.value })}
        />
      </Field>
      <Field label="CD 号" hideLabel>
        <input
          type="search"
          name="recordNo"
          placeholder="输入全部或部分 CD 号"
          value={draft.recordNo}
          onChange={(event) => setDraft({ ...draft, recordNo: event.target.value })}
        />
      </Field>
      <Field label="子采购单号" hideLabel>
        <input
          type="search"
          name="purchaseOrderNo"
          placeholder="输入全部或部分子采购单号"
          value={draft.purchaseOrderNo}
          onChange={(event) => setDraft({ ...draft, purchaseOrderNo: event.target.value })}
        />
      </Field>
    </FilterBar>
  );
}
