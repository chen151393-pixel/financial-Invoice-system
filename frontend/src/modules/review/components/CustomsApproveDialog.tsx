import { useId, useRef, useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog } from "../../../shared/components/ui";
import { approveCustomsReceipts } from "../customs-api";
import type { CustomsApproveResult, CustomsReceipt } from "../customs-types";

/** 确认当前页实际范围；提交后逐张显示真实结果，失败后也刷新以核实部分成功。 */
export function CustomsApproveDialog({
  items,
  onClose,
  onChanged,
}: {
  items: CustomsReceipt[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CustomsApproveResult | null>(null);
  const lock = useRef(false);
  const noteId = useId();
  async function submit() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      setResult(await approveCustomsReceipts(items, note));
    } catch (error) {
      setError(`${error instanceof Error ? error.message : "审核请求失败"}；请关闭窗口刷新核实后再操作。`);
    } finally {
      onChanged();
      setBusy(false);
      // 保持本次确认只能提交一次，避免网络结果不明时盲目重试。
    }
  }
  return (
    <Dialog
      title={result ? "海关审核结果" : "海关审核通过"}
      busy={busy}
      onClose={onClose}
      className="cm-approve"
    >
      <div className="cm-approve__body">
        <p className="cm-approve__hint">
          本次仅处理当前页选定的 {items.length}{" "}
          张回执。海关与财务两项当前版本均审核通过后，系统自动生成开票任务。
        </p>
        {!result && (
          <DataTable
            label="本次海关审核范围"
            rows={items}
            rowKey={(item) => String(item.id)}
            minWidth={360}
            density="compact"
            maxHeight={260}
            columns={[
              { key: "number", header: "出口报关单号", width: "65%", render: (item) => item.declarationNo },
              {
                key: "status",
                header: "明细比对",
                render: (item) => (
                  <Badge
                    tone={
                      item.status === "matched" || item.status === "split_matched" ? "success" : "warning"
                    }
                  >
                    {item.statusLabel}
                  </Badge>
                ),
              },
            ]}
          />
        )}
        {!result && (
          <div className="cm-approve__note">
            <label htmlFor={noteId}>人工审核说明</label>
            <p id={`${noteId}-hint`}>差异单必填，其余选填；本次说明应用于全部选中回执。</p>
            <textarea
              id={noteId}
              aria-describedby={`${noteId}-hint`}
              rows={3}
              placeholder="填写本次审核说明"
              value={note}
              maxLength={300}
              disabled={busy || !!error}
              onChange={(event) => setNote(event.target.value)}
            />
            <span className="cm-approve__limit">最多 300 字</span>
          </div>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        {result && (
          <>
            <Alert tone={result.skipped.length ? "warning" : "success"}>
              审核通过 {result.approved.length} 张，跳过 {result.skipped.length} 张。
            </Alert>
            <DataTable
              label="逐张审核结果"
              rows={[
                ...result.approved.map((item) => ({ ...item, outcome: "审核通过" })),
                ...result.skipped.map((item) => ({ ...item, outcome: item.reason })),
              ]}
              rowKey={(item) => String(item.id)}
              minWidth={360}
              columns={[
                { key: "number", header: "回执", render: (item) => item.declarationNo || `回执 ${item.id}` },
                { key: "outcome", header: "结果", render: (item) => item.outcome },
              ]}
            />
          </>
        )}
      </div>
      <div className="cm-approve__footer">
        <Button disabled={busy} onClick={onClose}>
          {result || error ? "关闭" : "取消"}
        </Button>
        {!result && !error && (
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "审核中…" : "确认审核通过"}
          </Button>
        )}
      </div>
    </Dialog>
  );
}
