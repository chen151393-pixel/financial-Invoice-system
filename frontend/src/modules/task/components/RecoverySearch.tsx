import { useState } from "react";
import { Button, Field, FilterBar, Segmented } from "../../../shared/components/ui";
import type { RecoveryBoard, RecoveryQuery } from "../types/recovery";

type Draft = Pick<RecoveryQuery, "memberId" | "companyId" | "supplierName" | "orderNo">;
const EMPTY: Draft = { memberId: "", companyId: "", supplierName: "", orderNo: "" };
const pick = (query: RecoveryQuery): Draft => ({
  memberId: query.memberId,
  companyId: query.companyId,
  supplierName: query.supplierName,
  orderNo: query.orderNo,
});
const same = (left: Draft, right: Draft) =>
  (Object.keys(EMPTY) as (keyof Draft)[]).every((key) => left[key] === right[key]);

/** 一行查询栏：开票月份点选即生效，其余条件点「查询」后生效。 */
export function RecoverySearch({
  board,
  query,
  busy,
  onSearch,
  onRefresh,
}: {
  board: RecoveryBoard;
  query: RecoveryQuery;
  busy: boolean;
  onSearch: (query: RecoveryQuery) => void;
  onRefresh: () => void;
}) {
  const applied = pick(query);
  const [draft, setDraft] = useState(applied);
  const [synced, setSynced] = useState(applied);
  // 地址恢复或清除条件时同步输入值，保持控件挂载以免丢失焦点。
  if (!same(synced, applied)) {
    setSynced(applied);
    setDraft(applied);
  }
  const edited = !same(draft, applied);
  const filtered = Object.values(applied).some(Boolean);
  const month = query.month || board.defaultMonth;
  const months = [
    { value: "all", label: "全部" },
    ...board.months.map((item) => ({ value: item.month, label: item.label })),
  ];
  if (!months.some((item) => item.value === month)) {
    const option = board.options.months.find((item) => item.id === month);
    months.push({ value: month, label: option?.name ?? month });
  }
  return (
    <FilterBar
      onSubmit={() => {
        if (!busy) onSearch({ ...query, ...draft, page: 1 });
      }}
      pending={edited ? "条件已修改，点击「查询」生效；多个条件同时满足" : undefined}
      actions={
        <>
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? "查询中…" : "查询"}
          </Button>
          <Button
            disabled={busy || (!filtered && !edited)}
            onClick={() => {
              setDraft(EMPTY);
              onSearch({ ...query, ...EMPTY, page: 1 });
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
      <div className="ui-field rv-month">
        <span>开票月份</span>
        <Segmented
          label="开票月份"
          value={month}
          options={months}
          disabled={busy}
          onChange={(value) => onSearch({ ...query, month: value, page: 1 })}
        />
      </div>
      <Field label="采购员">
        <select
          name="memberId"
          value={draft.memberId}
          onChange={(event) => setDraft({ ...draft, memberId: event.target.value })}
        >
          <option value="">全部采购员</option>
          {board.options.buyers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="采购抬头">
        <select
          name="companyId"
          value={draft.companyId}
          onChange={(event) => setDraft({ ...draft, companyId: event.target.value })}
        >
          <option value="">全部抬头</option>
          {board.options.companies.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="供应商" grow>
        <input
          type="search"
          name="supplierName"
          placeholder="供应商名称或关键词"
          value={draft.supplierName}
          onChange={(event) => setDraft({ ...draft, supplierName: event.target.value })}
        />
      </Field>
      <Field label="CD 号 / 子采购单号" grow>
        <input
          type="search"
          name="orderNo"
          placeholder="全部或部分单号，多个用逗号分隔"
          value={draft.orderNo}
          onChange={(event) => setDraft({ ...draft, orderNo: event.target.value })}
        />
      </Field>
    </FilterBar>
  );
}
