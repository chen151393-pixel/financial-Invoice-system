import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Dialog } from "../../../shared/components/ui";
import type { DeliveryController } from "../types/delivery";
import { formatTime } from "./format";

export function WecomNotification({ controller: ui }: { controller: DeliveryController }) {
  const [reason, setReason] = useState("");
  const latest = ui.items[0];
  return (
    <section className="itn-history task-wecom" aria-label="企微群发">
      <h3>企微群发</h3>
      <p className="it-help">
        从已归档合同上传附件，提交后由群主在企微确认。目标群以预览中的供应商绑定为准。
      </p>
      {ui.error && <p role="alert">{ui.error}</p>}
      {ui.loading ? (
        <p role="status">正在读取发送记录…</p>
      ) : !latest ? (
        <p>暂无企微提交记录。</p>
      ) : (
        <>
          <p role="status">
            <strong>{latest.statusLabel}</strong>
          </p>
          <dl className="itn-facts itn-record-facts">
            <dt>目标群</dt>
            <dd>
              {latest.groupName} · {latest.chatId}
            </dd>
            <dt>群主</dt>
            <dd>
              {latest.employee} · {latest.userid}
            </dd>
            <dt>提交时间</dt>
            <dd>{latest.submittedAt ? formatTime(latest.submittedAt) : "尚未提交"}</dd>
            <dt>最近查询</dt>
            <dd>{latest.lastCheckedAt ? formatTime(latest.lastCheckedAt) : "尚未查询"}</dd>
            <dt>消息编号</dt>
            <dd>{latest.msgid || "尚未取得"}</dd>
          </dl>
          {latest.error && <p role="alert">{latest.error}</p>}
        </>
      )}
      <div className="itn-actions" role="group" aria-label="发送记录操作">
        {latest && (
          <>
            <Button disabled={ui.busy || !latest.refresh.allowed} onClick={() => void ui.refresh(latest.id)}>
              刷新发送结果
            </Button>
            <Button
              disabled={ui.busy || !latest.reconcile.allowed}
              onClick={() => void ui.findCandidates(latest.id)}
            >
              核实发送记录
            </Button>
          </>
        )}
        <Button disabled={ui.busy || ui.loading} onClick={() => void ui.reload()}>
          重新读取记录
        </Button>
      </div>
      {latest && ui.candidates && (
        <div>
          <p>{ui.candidates.reason}</p>
          {ui.candidates.items.map((candidate) => (
            <div key={candidate.candidateId}>
              <p>
                {candidate.description} · {candidate.candidateId}
              </p>
              <label className="itn-field">
                核实说明
                <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              <Button disabled={ui.busy} onClick={() => void ui.reconcile(latest.id, candidate, reason)}>
                确认关联原群发
              </Button>
            </div>
          ))}
        </div>
      )}
      {ui.items.map((item) => (
        <details key={item.id}>
          <summary>
            版本 {item.revision} · {item.statusLabel} · {formatTime(item.createdAt)}
          </summary>
          <dl className="itn-facts itn-record-facts">
            <dt>企业 ID</dt>
            <dd>{item.corpId}</dd>
            <dt>目标群</dt>
            <dd>
              {item.groupName}（{item.chatId}）
            </dd>
            <dt>群主</dt>
            <dd>
              {item.employee} · {item.userid}
            </dd>
            <dt>合同</dt>
            <dd>
              {item.files.map((file) => (
                <div key={file.sha256 + file.filename}>{file.filename}</div>
              ))}
            </dd>
            <dt>渠道发送时间</dt>
            <dd>{item.sentAt ? formatTime(item.sentAt) : "尚无成功回执"}</dd>
          </dl>
          <pre>{item.message}</pre>
          {item.error && <p>{item.error}</p>}
        </details>
      ))}
      {ui.preview && (
        <Dialog className="itn-dialog" title="确认提交企微群发" busy={ui.busy} onClose={ui.closePreview}>
          <p>
            供应商：{ui.preview.supplier} · 采购公司：{ui.preview.company}
          </p>
          <p>子采购单：{ui.preview.orderNumbers.join("、")}</p>
          <p>
            目标群：{ui.preview.groupName}（{ui.preview.chatId}）
          </p>
          <p>
            群主：{ui.preview.employee} · {ui.preview.userid}
          </p>
          <pre>{ui.preview.message}</pre>
          <h4>随通知发送的合同</h4>
          <ul>
            {ui.preview.files.map((file) => (
              <li key={file.sha256 + file.filename}>
                {file.filename}（{file.size} 字节）
              </li>
            ))}
          </ul>
          <p>确认后上传合同并创建群发任务，仍需群主在企微确认。请确保群主使用 4.1.10 及以上客户端。</p>
          <Button
            variant="primary"
            disabled={ui.busy || !ui.preview.submit.allowed}
            onClick={() => void ui.submit()}
          >
            {ui.busy ? "正在提交…" : "提交，等待群主确认"}
          </Button>
        </Dialog>
      )}
    </section>
  );
}
