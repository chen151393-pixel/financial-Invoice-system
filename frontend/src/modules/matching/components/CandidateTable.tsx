import { Badge, Button, DataTable, Progress } from "../../../shared/components/ui";
import type { ManualOrderCandidate } from "../types/manual-order";

/** 候选以整张子采购单为最小单位，只能由用户选择；合计、置信度与限制全部来自后端。 */
export function CandidateTable({
  rows,
  chosenId,
  onChoose,
  busy = false,
}: {
  rows: ManualOrderCandidate[];
  chosenId: string | null;
  onChoose: (candidate: ManualOrderCandidate) => void;
  busy?: boolean;
}) {
  return (
    <DataTable
      label="候选子采购单"
      rows={rows}
      rowKey={(row) => row.purchaseOrderId}
      minWidth={640}
      density="compact"
      columns={[
        {
          key: "order",
          header: "子采购单 / 供应商",
          render: (row) => (
            <div className="matching-cell">
              <strong>
                {row.orderNo || "—"}
                {row.orderMatched && (
                  <>
                    {" "}
                    <Badge tone="success" dot={false}>
                      备注命中
                    </Badge>
                  </>
                )}
              </strong>
              {row.parentOrderNo && <small>母采购单 {row.parentOrderNo}</small>}
              <small>
                {row.supplier || "供应商未提供"}
                {row.recordNumbers.length > 0 && ` · ${row.recordNumbers.join("、")}`}
              </small>
            </div>
          ),
        },
        {
          key: "lines",
          header: "明细",
          align: "right",
          render: (row) => (
            <div className="matching-cell">
              <span>{row.lines.length} 行</span>
              <small>{row.unit || "单位缺失"}</small>
            </div>
          ),
        },
        {
          key: "remaining",
          header: "剩余应开数量 / 含税",
          align: "right",
          render: (row) => (
            <div className="matching-cell">
              <span>{row.remainingQuantity ?? "—"}</span>
              <strong>
                {row.remainingAmount ?? "—"} {row.currency}
              </strong>
            </div>
          ),
        },
        {
          key: "confidence",
          header: "置信度",
          width: "130px",
          render: (row) => (
            <Progress width={row.confidence} text={`${row.confidence}%`} label={`${row.orderNo}置信度`} />
          ),
        },
        {
          key: "choose",
          header: "操作",
          render: (row) => (
            <div className="matching-cell">
              <Button
                size="sm"
                aria-label={`选择子采购单 ${row.orderNo}`}
                disabled={busy || Boolean(row.block)}
                onClick={() => onChoose(row)}
              >
                {chosenId === row.purchaseOrderId ? "已选择" : "选择此单"}
              </Button>
              {row.block && <small>{row.block}</small>}
              {chosenId === row.purchaseOrderId && <Badge tone="info">待确认分配</Badge>}
            </div>
          ),
        },
      ]}
    />
  );
}
