import { useId, useState } from "react";
import { Badge, Button, Card, CardContent, Stepper } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { HkBatch } from "../types/hk-workbench";
import { BatchWorkspace } from "./BatchWorkspace";
export function HkBatchCard({ row, onChanged }: { row: HkBatch; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [flowOpen, setFlowOpen] = useState(true);
  const [mode, setMode] = useState<"none" | "remit">("none");
  const [actionVersion, setActionVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const id = useId();
  const flowId = useId();
  const batch = row.batch;
  return (
    <Card className="settlement-hk-batch" data-expanded={open || undefined}>
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
            ) : (
              <Button
                size="sm"
                variant="primary"
                aria-expanded={open}
                aria-controls={id}
                disabled={busy || (row.primaryAction === "remit" && !batch.actions.settle.allowed)}
                title={row.primaryAction === "remit" ? batch.actions.settle.reason : undefined}
                onClick={() => {
                  if (open) {
                    setOpen(false);
                    setMode("none");
                    return;
                  }
                  setOpen(true);
                  setActionVersion((value) => value + 1);
                  setMode(row.primaryAction === "remit" ? "remit" : "none");
                }}
              >
                {row.primaryLabel}
              </Button>
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
        <div id={id} hidden={!open}>
          {open && (
            <div className="settlement-hk-batch__workspace">
              <BatchWorkspace
                key={`${batch.id}:${actionVersion}`}
                batchId={batch.id}
                initialMode={mode}
                onChanged={onChanged}
                onBusyChange={setBusy}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
