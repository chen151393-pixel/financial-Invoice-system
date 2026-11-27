import { Badge, Card, CardContent, CardHeader } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BatchDetail } from "../types";

export function BatchOverview({ batch }: { batch: BatchDetail }) {
  return (
    <Card>
      <CardHeader
        title={
          <span className="settlement-badges">
            {batch.batchNo}
            <Badge tone={batch.route === "hk_transit" ? "info" : "neutral"}>{batch.routeLabel}</Badge>
            <Badge
              tone={
                batch.status === "settled" ? "success" : batch.status === "cancelled" ? "neutral" : "progress"
              }
            >
              {batch.statusLabel}
            </Badge>
          </span>
        }
        description={batch.consignee}
        actions={
          <div className="settlement-batch__total">
            <span>报关合计 · {batch.currency}</span>
            <strong>{money(batch.declaredTotal)}</strong>
          </div>
        }
      />
      <CardContent>
        <dl className="settlement-batch__facts">
          <div>
            <dt>到账日期</dt>
            <dd>{batch.receivedOn || "—"}</dd>
          </div>
          <div>
            <dt>香港到账 / 手续费</dt>
            <dd>
              {batch.currency} {money(batch.receivedAmount)} / {money(batch.receivedFee)}
            </dd>
            {batch.receivedSlipUrl && (
              <dd>
                <a href={batch.receivedSlipUrl} target="_blank" rel="noreferrer">
                  {batch.receivedSlipName || "查看银行水单"}
                </a>
              </dd>
            )}
          </div>
          <div>
            <dt>银行流水号</dt>
            <dd>{batch.receivedReference || "—"}</dd>
          </div>
          <div>
            <dt>关联报关单</dt>
            <dd>{batch.declarationCount} 张</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
