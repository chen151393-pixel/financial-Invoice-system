import { Badge, Button, DataTable, Progress } from "../../../shared/components/ui";
import type { Candidate } from "../types/matching";

/** 候选行只能由用户选择；限制与置信度全部来自后端。 */
export function CandidateTable({
  rows,
  chosenId,
  onChoose,
  busy = false,
}: {
  rows: Candidate[];
  name: string;
  chosenId: string | null;
  onChoose: (candidate: Candidate) => void;
  busy?: boolean;
}) {
  return (
    <DataTable
      label="候选子采购行"
      rows={rows}
      rowKey={(row) => row.purchase.purchaseLineId}
      minWidth={580}
      density="compact"
      columns={[
        {
          key: "purchase",
          header: "子采购单 / 品名",
          render: ({ purchase }) => (
            <div className="matching-cell">
              <strong>{purchase.orderNo || "—"}</strong>
              <small>
                {purchase.item || "—"} · {purchase.unit || "单位缺失"}
              </small>
              <small>
                {purchase.supplier} · {purchase.recordNumber}
              </small>
            </div>
          ),
        },
        {
          key: "remaining",
          header: "剩余应开数量 / 含税",
          align: "right",
          render: ({ purchase }) => (
            <div className="matching-cell">
              <span>{purchase.remainingQuantity ?? "—"}</span>
              <strong>
                {purchase.remainingAmount ?? "—"} {purchase.currency}
              </strong>
            </div>
          ),
        },
        {
          key: "confidence",
          header: "置信度",
          width: "130px",
          render: (row) => (
            <Progress
              width={row.confidence}
              text={`${row.confidence}%`}
              label={`${row.purchase.orderNo}置信度`}
            />
          ),
        },
        {
          key: "choose",
          header: "操作",
          render: (row) => (
            <div className="matching-cell">
              <Button size="sm" disabled={busy || Boolean(row.block)} onClick={() => onChoose(row)}>
                {chosenId === row.purchase.purchaseLineId ? "已选择" : "选用此行"}
              </Button>
              {row.block && <small>{row.block}</small>}
              {chosenId === row.purchase.purchaseLineId && <Badge tone="info">待确认分配</Badge>}
            </div>
          ),
        },
      ]}
    />
  );
}
