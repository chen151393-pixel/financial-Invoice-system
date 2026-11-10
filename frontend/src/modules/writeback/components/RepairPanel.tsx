import { useState } from "react";
import { Button, Card, CardContent, CardHeader, Dialog } from "../../../shared/components/ui";
import type { TaskDetail } from "../types";

const HINT =
  "适用于 NS 权限不足等原因导致账单未更新的情况。请先在 NS 处理原因（例如为回写角色开通“账单”编辑权限）；" +
  "已在 NS 手工补齐的，可直接在下方核实后标记结果。";
const SAFETY =
  "NS 会先核对发票记录、明细金额与账单写前累计，任一不符则不改动任何账单。" +
  "若结果不明，任务会停在“结果不明”，须在 NS 核实后标记，不会自动重试。";

/**
 * 账单补写（2026-11-10）：NS 已建发票记录、账单累计未全部更新时，只补写账单，不新建发票记录。
 * 能否补写由后端 repair.allowed/reason 决定；NS 端再核对发票记录明细与账单写前累计，不符时不改动。
 */
export function RepairPanel({
  task,
  busy,
  writing = false,
  onRepair,
}: {
  task: TaskDetail;
  busy: boolean;
  writing?: boolean;
  onRepair: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const record = task.request?.nsRecordId;
  if (task.state !== "partial" || !record) return null;
  const allowed = Boolean(task.actions.repair);
  return (
    <Card>
      <CardHeader
        title="补写 NS 账单"
        description={`发票记录 ${record} 已在 NS 建成；补写只更新账单的累计已收发票金额与关联发票，不会再建发票记录。`}
        actions={
          <Button variant="primary" disabled={busy || writing || !allowed} onClick={() => setAsking(true)}>
            {writing ? "正在补写…" : "补写账单"}
          </Button>
        }
      />
      <CardContent>
        {!allowed && <p className="wb-secondary">暂不能补写：{task.repair?.reason || "请刷新任务状态"}</p>}
        <p className="wb-secondary">{HINT}</p>
      </CardContent>
      {asking && (
        <Dialog title="确认补写 NS 账单" busy={busy || writing} onClose={() => setAsking(false)}>
          <p>{`将把发票记录 ${record} 写入其明细中的账单：仍为写前累计的账单补写累计已收发票金额与关联发票，已补齐的账单跳过。`}</p>
          <p className="wb-secondary">{SAFETY}</p>
          <div className="wb-dialog-actions">
            <Button disabled={busy || writing} onClick={() => setAsking(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={busy || writing}
              onClick={() => {
                if (busy || writing) return;
                setAsking(false);
                onRepair();
              }}
            >
              确认补写
            </Button>
          </div>
        </Dialog>
      )}
    </Card>
  );
}
