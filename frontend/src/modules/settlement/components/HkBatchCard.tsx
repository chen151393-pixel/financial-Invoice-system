import { useId, useState } from "react";
import { Link, useLocation } from "react-router";
import { settlementHkBatchPath } from "../../../app/paths";
import { Badge, Button, Card, CardContent, Stepper } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { HkBatch } from "../types/hk-workbench";
export function HkBatchCard({ row }: { row: HkBatch }) {
  const location = useLocation();
  const [flowOpen, setFlowOpen] = useState(true);
  const flowId = useId();
  const batch = row.batch;
  return (
    <Card className="settlement-hk-batch">
      <CardContent>
        <div className="settlement-hk-batch__summary">
          <div className="settlement-hk-batch__identity">
            <div className="settlement-hk-batch__title">
              <strong>{batch.batchNo}</strong>
              <Badge
                tone={
                  batch.status === "settled"
                    ? "success"
                    : batch.status === "cancelled"
                      ? "neutral"
                      : "progress"
                }
              >
                {batch.statusLabel}
              </Badge>
            </div>
            <span>{batch.consignee}</span>
            <small>
              {batch.declarationCount} 张报关单 · 到账 {batch.receivedOn} ·{" "}
              {batch.receivedReference || "流水号未填写"}
            </small>
          </div>
          <div className="settlement-hk-batch__amount">
            <small>报关合计 · {batch.currency}</small>
            <strong>{money(batch.declaredTotal)}</strong>
            <small>
              香港到账 {money(batch.receivedAmount)} + 手续费 {money(batch.receivedFee)}
            </small>
          </div>
          <div className="settlement-hk-batch__documents">
            <small>资料</small>
            <div className="settlement-badges">
              {row.documents.map((flag) => (
                <Badge key={flag.label} tone={flag.ready ? "success" : "warning"}>
                  {flag.label} · {flag.ready ? "齐" : "待补"}
                </Badge>
              ))}
            </div>
            <span data-overdue={row.overdue || undefined}>{row.waitingLabel}</span>
          </div>
          <div className="settlement-hk-batch__actions">
            {row.primaryAction === "package" ? (
              row.package.allowed ? (
                <a className="ui-button ui-button--primary ui-button--sm" href={row.packageUrl} download>
                  下载资料包
                </a>
              ) : (
                <Button size="sm" disabled title={row.package.reason}>
                  下载资料包
                </Button>
              )
            ) : row.primaryAction === "remit" && !batch.actions.settle.allowed ? (
              <Button size="sm" variant="primary" disabled title={batch.actions.settle.reason}>
                {row.primaryLabel}
              </Button>
            ) : (
              <Link
                className="ui-button ui-button--primary ui-button--sm"
                to={settlementHkBatchPath(batch.id, row.primaryAction === "remit")}
                state={{ hkReturnTo: location.pathname + location.search }}
              >
                {row.primaryLabel}
              </Link>
            )}

            <Button
              size="sm"
              variant="ghost"
              aria-expanded={flowOpen}
              aria-controls={flowId}
              onClick={() => setFlowOpen((value) => !value)}
            >
              {flowOpen ? "收起流程" : "展开流程"}
            </Button>
          </div>
        </div>
        <div id={flowId} hidden={!flowOpen}>
          <div className="settlement-hk-batch__flow">
            <Stepper label={`批次 ${batch.batchNo} 处理流程`} steps={row.steps} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
