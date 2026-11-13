import { Badge, Button, DataTable } from "../../../shared/components/ui";
import type { Column } from "../../../shared/components/ui";
import type { OwnerItem } from "../types/supplier-owner";

export const ownerKey = (row: OwnerItem) => `${row.supplierId}:${row.companyId}`;
export function SupplierOwnerTable({
  items,
  selected,
  disabled,
  onSelect,
  onEdit,
  onHistory,
}: {
  items: OwnerItem[];
  selected: string[];
  disabled: boolean;
  onSelect: (keys: string[]) => void;
  onEdit: (row: OwnerItem) => void;
  onHistory: (row: OwnerItem) => void;
}) {
  const all = items.length > 0 && items.every((r) => selected.includes(ownerKey(r)));
  const columns: Column<OwnerItem>[] = [
    {
      key: "select",
      width: "44px",
      header: (
        <input
          type="checkbox"
          aria-label="选择本页全部关系"
          checked={all}
          disabled={disabled}
          onChange={(e) => onSelect(e.target.checked ? items.map(ownerKey) : [])}
        />
      ),
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`选择 ${r.supplierName} / ${r.companyName}`}
          disabled={disabled}
          checked={selected.includes(ownerKey(r))}
          onChange={(e) =>
            onSelect(
              e.target.checked ? [...selected, ownerKey(r)] : selected.filter((key) => key !== ownerKey(r)),
            )
          }
        />
      ),
    },
    {
      key: "supplier",
      header: "供应商",
      render: (r) => (
        <>
          <strong>{r.supplierName}</strong>
          <small className="supplier-owner-secondary">
            {r.account} · NS {r.nsInternalId}
          </small>
        </>
      ),
    },
    { key: "company", header: "采购抬头", render: (r) => r.companyName },
    {
      key: "member",
      header: "负责人",
      render: (r) => (
        <>
          {r.current?.memberName || "待分配"}
          {r.scheduled.map((v) => (
            <small key={v.id} className="supplier-owner-secondary">
              {v.effectiveDate} 起：{v.memberName}
            </small>
          ))}
        </>
      ),
    },
    { key: "date", header: "生效日期", render: (r) => r.current?.effectiveDate || "—" },
    {
      key: "status",
      header: "状态",
      render: (r) => (
        <Badge tone={r.current ? "success" : "warning"}>
          {r.current ? "已关联" : r.scheduled.length ? "待生效" : "未关联"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "操作",
      render: (r) => (
        <div className="supplier-owner-actions">
          <Button size="sm" disabled={disabled} onClick={() => onEdit(r)}>
            {r.revision ? "维护" : "分配"}
          </Button>
          <Button size="sm" onClick={() => onHistory(r)}>
            历史
          </Button>
        </div>
      ),
    },
  ];
  return (
    <DataTable
      label="供应商人员关联"
      columns={columns}
      rows={items}
      rowKey={ownerKey}
      minWidth={960}
      density="compact"
    />
  );
}
