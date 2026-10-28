import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  Stepper,
  type Column,
} from "../../../shared/components/ui";
import { demoInvoices, demoTasks, type DemoCheck } from "./workflow-data";

export function DemoInvoiceReview({ taskId, onBack }: { taskId?: string; onBack: () => void }) {
  const queue = demoInvoices.filter((invoice) => !taskId || invoice.taskId === taskId);
  const [index, setIndex] = useState(0);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [onlyDifferences, setOnlyDifferences] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [finished, setFinished] = useState(false);
  const invoice = queue[index];
  if (!invoice)
    return <EmptyState title="没有关联样例发票" action={<Button onClick={onBack}>返回任务</Button>} />;
  const task = demoTasks.find((item) => item.id === invoice.taskId)!;
  const note = notes[invoice.id] ?? "";
  function advance(decision: string) {
    setDecisions((current) => ({ ...current, [invoice.id]: decision }));
    if (index + 1 < queue.length) setIndex(index + 1);
    else setFinished(true);
  }
  const columns: Column<DemoCheck>[] = [
    { key: "field", header: "核对项目", render: (check) => <strong>{check.field}</strong> },
    { key: "basis", header: "采购依据 · 审核版本 2", render: (check) => check.basis },
    { key: "invoice", header: "发票记录 · 版本 1", render: (check) => check.invoice },
    {
      key: "result",
      header: "校验结果",
      render: (check) => <Badge tone={check.different ? "warning" : "success"}>{check.result}</Badge>,
    },
  ];
  const rows = invoice.checks.filter((check) => !onlyDifferences || check.different);
  return (
    <div className="task-demo__review-layout">
      <Card>
        <CardHeader
          title={taskId ? "本任务关联发票" : "连续核票队列"}
          description="选择发票，或按顺序处理。"
        />
        <CardContent>
          <nav className="task-demo__invoice-nav" aria-label="样例发票队列">
            {queue.map((item, itemIndex) => (
              <button
                type="button"
                key={item.id}
                aria-current={!finished && index === itemIndex ? "true" : undefined}
                onClick={() => {
                  setIndex(itemIndex);
                  setFinished(false);
                }}
              >
                <strong>{item.number}</strong>
                <span>{item.product}</span>
                <span>{item.amount} CNY</span>
                <Badge tone={decisions[item.id] ? "neutral" : item.allowed ? "info" : "warning"}>
                  {decisions[item.id] ?? (item.allowed ? "待人工确认" : "需核实差异")}
                </Badge>
              </button>
            ))}
          </nav>
        </CardContent>
      </Card>
      <Card>
        {finished ? (
          <EmptyState
            icon="check"
            title="本轮核票演练结束"
            description="左侧保留本轮演练记录。正式发票、分配与任务进度均未改变；离开核票视图会清空演练记录。"
            action={<Button onClick={onBack}>收起核票内容</Button>}
          />
        ) : (
          <>
            <CardHeader
              title={`${invoice.number} · ${invoice.product}`}
              description={`${task.supplier} / ${task.order}`}
              actions={
                <Badge tone="neutral">
                  {index + 1} / {queue.length}
                </Badge>
              }
            />
            <CardContent>
              <Stepper
                label="样例核票流程"
                compact
                steps={[
                  { key: "source", label: "采购已审核", state: "done" },
                  { key: "invoice", label: "发票已到", state: "done" },
                  { key: "review", label: "人工核票", state: "current" },
                  { key: "receipt", label: "更新收票", state: "waiting" },
                ]}
              />
              <Alert
                title={invoice.allowed ? "未发现差异" : "先核实单位，再确认分配"}
                tone={invoice.allowed ? "info" : "warning"}
              >
                {invoice.reason}
              </Alert>
              <div className="task-demo__toolbar">
                <strong>依据与发票并排核对</strong>
                <label className="task-demo__checkbox">
                  <input
                    type="checkbox"
                    checked={onlyDifferences}
                    onChange={(event) => setOnlyDifferences(event.target.checked)}
                  />
                  只看差异
                </label>
              </div>
              {rows.length ? (
                <DataTable
                  label="样例发票逐项核对"
                  columns={columns}
                  rows={rows}
                  rowKey={(check) => check.field}
                  minWidth={600}
                />
              ) : (
                <EmptyState
                  title="本张样例发票没有差异项"
                  description="取消“只看差异”可以查看完整核对依据。"
                />
              )}
              <label className="task-demo__note">
                核实备注（仅演示）
                <textarea
                  value={note}
                  onChange={(event) =>
                    setNotes((current) => ({ ...current, [invoice.id]: event.target.value }))
                  }
                  rows={2}
                  placeholder="例如：需供应商提供该规格的装箱数量证明"
                />
              </label>
              <p className="task-demo__muted">
                同一任务的多张票逐张核对；金额、数量与是否可通过均为预置样例。
              </p>
            </CardContent>
            <CardFooter className="task-demo__review-actions">
              <Button variant="secondary" onClick={onBack}>
                返回任务
              </Button>
              <Button
                variant="secondary"
                onClick={() => advance(note ? "演练待核实（有备注）" : "演练待核实")}
              >
                演练留待核实并继续
              </Button>
              <Button
                disabled={!invoice.allowed || Boolean(decisions[invoice.id])}
                title={!invoice.allowed ? invoice.reason : undefined}
                onClick={() => advance("演练已通过")}
              >
                演练通过并下一条
              </Button>
            </CardFooter>
          </>
        )}
      </Card>
    </div>
  );
}
