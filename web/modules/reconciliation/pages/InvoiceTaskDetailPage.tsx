import { useEffect, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { openLocalSession } from "../../identity/api";
import { getInvoiceTask, prepareInvoiceTaskDocument } from "../api";
import { TaskNotification } from "../components/TaskNotification";
import type { InvoiceTaskDetail } from "../task-types";
import "./invoice-task.css";
import "./invoice-task-detail.css";

const sections = {
  review: "财务审核",
  documents: "开票资料",
  notification: "通知供应商",
  invoices: "等待收票",
  comparison: "比对结果",
  completion: "完成情况",
  history: "流转记录",
};
const stepSections = ["review", "documents", "notification", "invoices", "comparison", "completion"] as const;
function readSection(): Section {
  const key = window.location.hash.replace("#task-", "");
  return Object.hasOwn(sections, key) ? (key as Section) : "documents";
}
type Section = keyof typeof sections;
type Remote =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: InvoiceTaskDetail };
const date = (value: string) => new Date(value).toLocaleString("zh-CN");

export function InvoiceTaskDetailPage({ id }: { id: string }) {
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [section, setSection] = useState<Section>(readSection);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getInvoiceTask(id);
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "任务加载失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [id, refresh]);

  useEffect(() => {
    const sync = () => setSection(readSection());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  function navigate(next: Section) {
    setSection(next);
    window.location.hash = `task-${next}`;
  }

  async function prepare(orderId: string) {
    if (busy) return;
    setBusy(orderId);
    setFeedback(null);
    try {
      const data = await prepareInvoiceTaskDocument(id, orderId);
      setState({ kind: "ready", data });
      setFeedback({ error: false, text: "子采购合同已保存到共享盘。" });
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "获取原件失败，流程未推进" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="it-page itd-page">
      <a className="itd-back" href="/invoice-followup">
        ← 返回全部任务
      </a>
      {state.kind === "loading" ? (
        <p role="status" className="itd-panel">
          正在加载任务并核验审核来源…
        </p>
      ) : state.kind === "error" ? (
        <div className="itd-panel" role="alert">
          <p>{state.message}</p>
          <Button
            onClick={() => {
              setState({ kind: "loading" });
              setRefresh((n) => n + 1);
            }}
          >
            重新加载
          </Button>
        </div>
      ) : (
        (() => {
          const detail = state.data;
          const task = detail.task;
          return (
            <>
              <section className="itd-panel" aria-label="任务概览">
                <header className="itd-heading">
                  <div>
                    <p className="it-help">
                      {task.recordNumber} · 审核版本 {task.reviewRevision}
                    </p>
                    <h2>{task.supplier}</h2>
                    <p>
                      {task.company} · {task.orderNumbers.join("、")}
                    </p>
                  </div>
                  <span className="it-status">{task.statusLabel}</span>
                </header>
                <ol className="it-steps">
                  {detail.steps.map((step, index) => (
                    <li
                      key={step.label}
                      data-state={step.state}
                      aria-current={step.state === "current" ? "step" : undefined}
                    >
                      <button
                        type="button"
                        className="itd-step-link"
                        aria-pressed={section === stepSections[index]}
                        onClick={() => navigate(stepSections[index])}
                      >
                        <span className="itd-step-number" aria-hidden="true">
                          {step.state === "done" ? "✓" : index + 1}
                        </span>
                        <strong>{step.label}</strong>
                        <span>{step.description}</span>
                      </button>
                    </li>
                  ))}
                </ol>
                <div className="itd-current">
                  <div>
                    <strong>{task.reason}</strong>
                    <p>{detail.prepare.reason}</p>
                  </div>
                  <a
                    className="ui-button ui-button--secondary"
                    href="#task-documents"
                    onClick={() => navigate("documents")}
                  >
                    查看开票资料
                  </a>
                </div>
                <dl className="itd-facts">
                  <div>
                    <dt>审核来源环境</dt>
                    <dd>{task.account}</dd>
                  </div>
                  <div>
                    <dt>原件下载环境</dt>
                    <dd>{detail.downloadEnvironment || "未配置"}</dd>
                  </div>
                  <div>
                    <dt>任务生成时间</dt>
                    <dd>{date(task.createdAt)}</dd>
                  </div>
                  <div>
                    <dt>审核采购明细</dt>
                    <dd>{task.lineCount} 行</dd>
                  </div>
                </dl>
                <p className="it-help" role="status">
                  {detail.sourceMessage}
                </p>
              </section>
              <section className="itd-panel" id={`task-${section}`} aria-label="任务资料与记录">
                <div className="itd-tabs" role="group" aria-label="任务内容切换">
                  {(Object.entries(sections) as [Section, string][]).map(([key, label]) => (
                    <Button key={key} aria-pressed={section === key} onClick={() => navigate(key)}>
                      {label}
                    </Button>
                  ))}
                </div>
                {feedback && (
                  <p className="itd-feedback" role={feedback.error ? "alert" : "status"}>
                    {feedback.text}
                  </p>
                )}
                {section === "review" && (
                  <div className="itd-content">
                    <h3>财务审核已通过</h3>
                    <p>
                      报关单：{task.recordNumber} · 审核版本 {task.reviewRevision}
                    </p>
                    <p>{detail.sourceMessage}</p>
                    <p className="it-reference">审核快照：{task.snapshotId}</p>
                    <Button onClick={() => navigate("documents")}>查看审核采购明细及合同</Button>
                  </div>
                )}
                <div hidden={section !== "notification"}>
                  <TaskNotification
                    key={`${task.id}:${detail.notification.revision}`}
                    detail={detail}
                    onUpdate={(data) => {
                      setState({ kind: "ready", data });
                      setFeedback({
                        error: false,
                        text:
                          data.task.status === "awaiting_invoice"
                            ? "已保存人工发送登记，任务进入等待收票。"
                            : "通知已保存，尚未向企微发送。",
                      });
                    }}
                  />
                </div>
                {section === "completion" && (
                  <div className="itd-placeholder">
                    <h3>任务尚未完成</h3>
                    <p>收票与比对尚未接入，当前不能完成开票任务。</p>
                  </div>
                )}
                {section === "documents" && (
                  <div className="itd-content">
                    <div>
                      <h3>子采购合同</h3>
                      <p className="it-help">
                        合同统一保存到共享盘，按下载日期建立文件夹，文件名为“子采购订单号+供应商.pdf”。
                      </p>
                    </div>
                    {detail.documents.length === 0 && <p>此任务没有可下载的子采购订单。</p>}
                    {detail.documents.map((doc) => (
                      <div key={doc.orderId} className="itd-document">
                        <span className="itd-file-type" aria-hidden="true">
                          PDF
                        </span>
                        <div className="itd-document__info">
                          <strong>{doc.orderNumber || "子采购单编号缺失"}</strong>
                          <p>
                            {doc.status === "ready"
                              ? `已保存到共享盘 · ${date(doc.archivedAt!)} · NS ${doc.environment} / ${doc.nsId}`
                              : doc.status === "archive_pending"
                                ? "待保存到共享盘（原件已暂存）"
                                : `待保存 · NS 环境 ${doc.environment || "未配置"}`}
                          </p>
                          <p>{doc.prepare.reason}</p>
                          {doc.archivePath && <p className="it-reference">保存路径：{doc.archivePath}</p>}
                        </div>
                        {doc.status !== "ready" && (
                          <Button
                            variant="primary"
                            disabled={!doc.prepare.allowed || busy !== null}
                            onClick={() => void prepare(doc.orderId)}
                          >
                            {busy === doc.orderId ? "正在保存到共享盘…" : "保存到共享盘"}
                          </Button>
                        )}
                      </div>
                    ))}
                    {detail.reasons.map((reason) => (
                      <p className="it-help" key={reason}>
                        {reason}
                      </p>
                    ))}
                    <details className="it-source-lines">
                      <summary>审核时采购明细（{task.lineCount} 行）</summary>
                      <p className="it-help">
                        保留审核时的采购原始数量和金额；合同开票内容以下载的原件为准。
                      </p>
                      <div
                        className="it-table-wrap"
                        role="region"
                        aria-label="审核时采购明细，可横向滚动"
                        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
                        tabIndex={0}
                      >
                        <table>
                          <thead>
                            <tr>
                              <th>子采购单</th>
                              <th>品名</th>
                              <th>原始数量</th>
                              <th>原始金额</th>
                              <th>币种</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detail.lines.map((line) => (
                              <tr key={`${line.order}:${line.id}`}>
                                <td>{line.order || "—"}</td>
                                <td>{line.name || "—"}</td>
                                <td>
                                  {line.quantity || "—"} {line.unit}
                                </td>
                                <td>{line.amount || "—"}</td>
                                <td>{line.currency || "来源未提供"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                    <div className="itd-next">
                      <div>
                        <h3>下一步：通知供应商开票</h3>
                        <p>{detail.notify.reason}</p>
                      </div>
                      <Button onClick={() => navigate("notification")}>通知供应商</Button>
                    </div>
                  </div>
                )}
                {section === "invoices" && (
                  <div className="itd-placeholder">
                    <h3>等待关联供应商发票</h3>
                    <p>任务与收票的关联尚未接入，当前不展示收票数量。</p>
                  </div>
                )}
                {section === "comparison" && (
                  <div className="itd-placeholder">
                    <h3>收票后进行比对</h3>
                    <p>{detail.compare.reason}</p>
                  </div>
                )}
                {section === "history" && (
                  <div className="itd-content">
                    <h3>已发生的流程记录</h3>
                    <ol className="itd-history">
                      {detail.notification.history
                        .filter((event) => event.sentAt)
                        .map((event) => (
                          <li key={event.revision}>
                            <strong>人工登记已发送通知</strong>
                            <p>
                              {date(event.at)} · 操作人 {event.actor}
                            </p>
                            <p>
                              外部群：{event.groupName} · 发送员工：{event.employee}
                            </p>
                            <p>{event.note}</p>
                            <Button onClick={() => navigate("notification")}>查看通知记录</Button>
                          </li>
                        ))}
                      <li>
                        <strong>财务审核通过，生成开票任务</strong>
                        <p>
                          {date(task.createdAt)} · 审核版本 {task.reviewRevision}
                        </p>
                      </li>
                      {detail.documents
                        .filter((doc) => doc.downloadedAt)
                        .map((doc) => (
                          <li key={doc.orderId}>
                            <strong>获取子采购合同：{doc.orderNumber}</strong>
                            <p>
                              {date(doc.downloadedAt!)} · NS {doc.environment} / {doc.nsId}
                            </p>
                            {doc.archivedAt && <p>保存到共享盘：{date(doc.archivedAt)}</p>}
                            {doc.archivePath && <p className="it-reference">{doc.archivePath}</p>}
                            <p className="it-reference">文件 SHA-256：{doc.sha256}</p>
                          </li>
                        ))}
                    </ol>
                    <p className="it-reference">
                      任务：{task.id}
                      <br />
                      审核快照：{task.snapshotId}
                    </p>
                  </div>
                )}
              </section>
            </>
          );
        })()
      )}
    </div>
  );
}
