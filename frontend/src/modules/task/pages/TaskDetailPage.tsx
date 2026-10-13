import { useEffect, useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { openLocalSession } from "../../identity/api";
import { getTask, prepareTaskDocument, recordTaskNotification, saveTaskNotification } from "../api/task";
import { TaskDocuments } from "../components/TaskDocuments";
import { TaskHistory } from "../components/TaskHistory";
import { TaskNotification } from "../components/TaskNotification";
import { sectionLabels, TaskOverview, type Section } from "../components/TaskOverview";
import type { NotificationDraft, NotificationRecord, TaskDetail } from "../types/task";
import "./task.css";
import "./task-detail.css";

function readSection(): Section {
  const key = window.location.hash.replace("#task-", "");
  return Object.hasOwn(sectionLabels, key) ? (key as Section) : "documents";
}
type Remote = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: TaskDetail };
type Feedback = { error: boolean; text: string } | null;

function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <div className="itd-placeholder">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

export function TaskDetailPage({ id }: { id: string }) {
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [section, setSection] = useState<Section>(readSection);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getTask(id);
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
      const data = await prepareTaskDocument(id, orderId);
      setState({ kind: "ready", data });
      setFeedback({ error: false, text: "子采购合同已保存到共享盘。" });
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "获取原件失败，流程未推进" });
    } finally {
      setBusy(null);
    }
  }
  // 通知组件只收集输入；请求在页面发起，结果以后端返回的任务详情为准。
  async function saveNotification(draft: NotificationDraft) {
    const data = await saveTaskNotification(id, draft);
    setState({ kind: "ready", data });
    setFeedback({ error: false, text: "通知已保存，尚未向企微发送。" });
  }
  async function recordNotification(record: NotificationRecord) {
    const data = await recordTaskNotification(id, record);
    setState({ kind: "ready", data });
    setFeedback({ error: false, text: "已保存人工发送登记，任务进入等待收票。" });
  }

  if (state.kind === "loading")
    return (
      <div className="it-page itd-page">
        <p role="status" className="itd-panel">
          正在加载任务…
        </p>
      </div>
    );
  if (state.kind === "error")
    return (
      <div className="it-page itd-page">
        <Link className="itd-back" to={paths.tasks}>
          ← 返回全部任务
        </Link>
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
      </div>
    );
  const detail = state.data;
  return (
    <div className="it-page itd-page">
      <Link className="itd-back" to={paths.tasks}>
        ← 返回全部任务
      </Link>
      <TaskOverview detail={detail} section={section} onNavigate={navigate} />
      <section className="itd-panel" id={`task-${section}`} aria-label="任务资料与记录">
        <div className="itd-tabs" role="group" aria-label="任务内容切换">
          {(Object.entries(sectionLabels) as [Section, string][]).map(([key, label]) => (
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
              报关单：{detail.task.recordNumber || "报关单号缺失"} · 审核版本 {detail.task.reviewRevision}
            </p>
            <p>{detail.sourceMessage}</p>
            <Button onClick={() => navigate("documents")}>查看应开明细及合同</Button>
          </div>
        )}
        {section === "documents" && (
          <TaskDocuments
            detail={detail}
            busy={busy}
            onPrepare={(orderId) => void prepare(orderId)}
            onNotify={() => navigate("notification")}
          />
        )}
        <div hidden={section !== "notification"}>
          <TaskNotification
            key={`${detail.task.id}:${detail.notification.revision}:${detail.task.status}`}
            detail={detail}
            onSave={saveNotification}
            onRecord={recordNotification}
          />
        </div>
        {section === "invoices" && (
          <Placeholder
            title="等待关联供应商发票"
            text="收票进度由发票比对结果自动汇总，比对接入后在此展示。"
          />
        )}
        {section === "comparison" && <Placeholder title="收票后进行比对" text={detail.compare.reason} />}
        {section === "completion" && (
          <Placeholder
            title={detail.task.status === "completed" ? "任务已完成" : "任务尚未完成"}
            text="全部任务行结束（已收齐、人工按差异结束或超开）后，任务自动完成。"
          />
        )}
        {section === "history" && <TaskHistory detail={detail} />}
      </section>
    </div>
  );
}
