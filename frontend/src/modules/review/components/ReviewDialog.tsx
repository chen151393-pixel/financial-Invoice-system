import { CurrencyEvidenceForm } from "./CurrencyEvidenceForm";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { useState } from "react";
import { Button, DataTable } from "../../../shared/components/ui";
import { useDialog } from "../hooks/useDialog";
import type { ComparisonGroup, PurchaseLine, CurrencyEvidence } from "../types";

export function ReviewDialog({
  group,
  busy,
  error,
  onClose,
  onApprove,
}: {
  group: ComparisonGroup;
  busy: boolean;
  error: string;
  onClose: () => void;
  onApprove: (note: string, evidence: CurrencyEvidence[]) => void;
}) {
  const ref = useDialog();
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<CurrencyEvidence[]>([]);
  const approved = group.review.status === "approved";
  const reviewLines = [
    ...group.customsLines.flatMap((row) =>
      row.purchaseLines.map((line) => ({
        line,
        label: `报关第 ${row.lineNo} 行`,
        key: `${row.id}:${line.id}`,
      })),
    ),
    ...group.unlinkedLines.map((line) => ({ line, label: "关联子采购明细", key: `order:${line.id}` })),
  ];
  return (
    <dialog
      ref={ref}
      className="fr-dialog fr-dialog--group"
      aria-labelledby="finance-review-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <header>
        <div>
          <h2 id="finance-review-title">{approved ? "报关单审核记录" : "审核整张报关单"}</h2>
          <p>
            {group.recordNumber} · {group.pl}
          </p>
        </div>
        <button className="fr-close" disabled={busy} onClick={onClose} aria-label="关闭审核窗口">
          ×
        </button>
      </header>
      <div className="fr-dialog__body">
        <p className="fr-dialog__hint">
          {approved
            ? "该报关单审核结果已保存。"
            : "请核对本张报关单及关联子采购明细。通过后保存整单审核记录，冻结子采购的开票数量、单位和含税金额，并自动生成开票任务；数据变化时需刷新后重新审核。"}
        </p>
        {approved && (
          <p className="fr-dialog__hint" role="status">
            审核通过时已按供应商、采购公司和币种生成开票任务。
            <Link to={paths.tasks}>前往开票跟进查看</Link>
          </p>
        )}
        <div className="fr-scope-heading">
          <strong>本次审核范围</strong>
          <span>
            {group.customsCount} 条报关行 · {group.purchaseCount} 条采购明细
          </span>
        </div>
        <ul className="fr-scope-lines">
          {reviewLines.map(({ line, label, key }) => (
            <li key={key}>
              <div className="fr-scope-line__heading">
                <strong>{line.name}</strong>
                <small>{label}</small>
              </div>
              <p>
                {line.child} · {line.supplier}
              </p>
              <div className="fr-scope-line__values">
                <span>
                  {line.scope === "order" ? "子单数量" : "本次数量"}
                  <b>
                    {line.quantity} {line.unit}
                  </b>
                </span>
                <span>
                  {line.scope === "order" ? "订单金额" : "本次采购金额"} · {line.currency || "未提供币种"}
                  <b>{line.amount || "未提供"}</b>
                </span>
              </div>
            </li>
          ))}
        </ul>
        {reviewLines.some(({ line }) => line.scope === "order") && (
          <p className="fr-dialog__hint">
            开票口径为子采购的采购数量、单位和含税金额；金额缺失的行审核后只能人工按差异结束。
          </p>
        )}
        {group.currencyEvidenceSummary?.map((evidence) => (
          <p key={evidence} className="fr-status-note">
            已核实结算币种 · {evidence}
          </p>
        ))}
        {!approved && (
          <CurrencyEvidenceForm
            checks={group.currencyChecks ?? []}
            value={evidence}
            onChange={setEvidence}
            busy={busy}
          />
        )}
        {approved ? (
          <dl className="fr-record">
            <div>
              <dt>审核身份</dt>
              <dd>{group.review.reviewedBy}</dd>
            </div>
            <div>
              <dt>审核时间</dt>
              <dd>{group.review.reviewedAt}</dd>
            </div>
            <div>
              <dt>审核备注</dt>
              <dd>{group.review.note || "无备注"}</dd>
            </div>
          </dl>
        ) : (
          <label className="fr-note-label" htmlFor="finance-note">
            审核备注 <span>选填</span>
            <textarea
              id="finance-note"
              disabled={busy}
              rows={3}
              maxLength={300}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
        )}
        {group.review.reason && <p className="fr-error">{group.review.reason}</p>}
        {error && (
          <p className="fr-error" role="alert">
            {error}
          </p>
        )}
        {busy && <p role="status">正在保存审核结果，请稍候…</p>}
      </div>
      <footer>
        {approved && (
          <Button disabled title="供应商通知接口预留，尚未接入">
            通知供应商（预留）
          </Button>
        )}
        <Button disabled={busy} onClick={onClose}>
          {approved ? "关闭" : "取消"}
        </Button>
        {!approved && (
          <Button
            variant="primary"
            disabled={busy || !group.review.allowed}
            onClick={() => onApprove(note, evidence)}
          >
            {busy ? "保存中…" : "整单审核通过"}
          </Button>
        )}
      </footer>
    </dialog>
  );
}

export function PurchaseDialog({ line, onClose }: { line: PurchaseLine; onClose: () => void }) {
  const ref = useDialog();
  const fields = [
    ["子采购单", line.child],
    ["母采购单", line.parent],
    ["供应商", line.supplier],
    ["采购品名", line.name],
    ["型号", line.model],
    [line.scope === "order" ? "子单数量" : "本次数量", `${line.quantity} ${line.unit}`],
    ["采购单价", line.price],
    [line.scope === "order" ? "订单金额（未分摊）" : "本次采购金额", line.amount],
    ["采购币种", line.currency],
    ["来源说明", line.note],
  ];
  return (
    <dialog ref={ref} className="fr-dialog" onCancel={onClose} aria-labelledby="purchase-detail-title">
      <header>
        <div>
          <h2 id="purchase-detail-title">子采购明细</h2>
          <p>审核在所属报关单统一进行。</p>
        </div>
        <button className="fr-close" aria-label="关闭采购明细" onClick={onClose}>
          ×
        </button>
      </header>
      <div className="fr-dialog__body">
        <dl className="fr-detail">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || "来源未提供"}</dd>
            </div>
          ))}
        </dl>
        {Boolean(line.members?.length) && (
          <DataTable
            label="合并前采购明细"
            rows={line.members ?? []}
            rowKey={(member) => member.id}
            density="compact"
            minWidth={620}
            columns={[
              { key: "name", header: "采购品名", render: (member) => member.name },
              { key: "model", header: "规格型号", render: (member) => member.model || "—" },
              {
                key: "quantity",
                header: "原始数量",
                align: "right",
                render: (member) => member.quantity || "未提供",
              },
              { key: "unit", header: "单位", render: (member) => member.unit },
              {
                key: "price",
                header: "原含税单价",
                align: "right",
                render: (member) => member.price || "未提供",
              },
              {
                key: "amount",
                header: "原含税金额",
                align: "right",
                render: (member) => member.amount || "未提供",
              },
            ]}
          />
        )}
      </div>
      <footer>
        <Button onClick={onClose}>关闭</Button>
      </footer>
    </dialog>
  );
}
