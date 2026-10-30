import { Badge, DataTable, EmptyState } from "../../../shared/components/ui";
import type { Check } from "../types/matching";

export function ChecksTable({ checks, caption }: { checks: Check[]; caption: string }) {
  if (!checks.length)
    return <EmptyState title="没有系统比对记录" description="人工新建的分配请核对原始发票和子采购资料。" />;
  return (
    <DataTable
      label={caption}
      rows={checks}
      rowKey={(row) => row.key}
      minWidth={520}
      density="compact"
      columns={[
        { key: "label", header: "比对项", width: "18%", render: (row) => row.label },
        { key: "invoice", header: "发票", width: "26%", render: (row) => row.invoiceValue ?? "—" },
        { key: "purchase", header: "子采购", width: "26%", render: (row) => row.purchaseValue ?? "—" },
        {
          key: "result",
          header: "结果",
          render: (row) => (
            <div className="matching-cell">
              <span>
                <Badge tone={row.result === "match" ? "info" : "warning"}>{row.resultLabel}</Badge>
              </span>
              {row.differenceLabel && <span>{row.differenceLabel}</span>}
              {row.note &&
                (row.result === "match" ? (
                  <details className="matching-check-note">
                    <summary>查看说明</summary>
                    <small>{row.note}</small>
                  </details>
                ) : (
                  <small>{row.note}</small>
                ))}
            </div>
          ),
        },
      ]}
    />
  );
}
