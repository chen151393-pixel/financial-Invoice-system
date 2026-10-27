import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button, Card, CardContent, CardHeader, ErrorState, Skeleton } from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import {
  closeTaskLine,
  getTask,
  prepareDeclarationDocument,
  prepareTaskDocument,
  recordTaskNotification,
  saveTaskNotification,
} from "../api/task";
import { DeclarationDocuments } from "../components/DeclarationDocuments";
import { formatTime } from "../components/format";
import { SignedContractUpload } from "../components/SignedContractUpload";
import { SignedContracts } from "../components/SignedContracts";
import { TaskDocuments } from "../components/TaskDocuments";
import { TaskHistory } from "../components/TaskHistory";
import { TaskLines } from "../components/TaskLines";
import { TaskNotification } from "../components/TaskNotification";
import { TaskOverview, type Section } from "../components/TaskOverview";
import { useDelivery } from "../hooks/useDelivery";
import type {
  ClosureRequest,
  DeclarationDocumentType,
  NotificationDraft,
  NotificationRecord,
  TaskDetail,
} from "../types/task";
import "./task.css";
import "./task-detail.css";

const SECTIONS: readonly Section[] = [
  "review",
  "documents",
  "notification",
  "invoices",
  "comparison",
  "completion",
];

// 地址中的 #task-节点 优先（如从发票比对返回）；否则停在后端标记的当前节点
function hashSection(): Section | null {
  const key = window.location.hash.replace("#task-", "");
  return SECTIONS.find((item) => item === key) ?? null;
}
function currentSection(detail: TaskDetail): Section {
  return detail.steps.find((step) => step.state === "current")?.key ?? "completion";
}
type Remote = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: TaskDetail };
type Feedback = { error: boolean; text: string } | null;

/**
 * 开票任务详情：概览 + 六个节点；左侧「当前节点」卡片放该节点的处理内容（进入页面即停在当前节点），
 * 下方为应开明细与收票进度；右侧为完结资料、流转记录和任务信息。
 */
export function TaskDetailPage({ id }: { id: string }) {
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [chosen, setChosen] = useState<Section | null>(hashSection);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [uploading, setUploading] = useState(false);
  const detail = state.kind === "ready" ? state.data : null;
  const current = detail ? currentSection(detail) : "documents";
  const section = chosen ?? current;
  const deliveryChanged = useCallback(async () => {
    const data = await getTask(id);
    setState({ kind: "ready", data });
  }, [id]);
  const delivery = useDelivery(id, deliveryChanged, section === "notification");
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
    const sync = () => setChosen(hashSection());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  function navigate(next: Section) {
    setChosen(next);
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
  async function retryDeclaration(type: DeclarationDocumentType) {
    if (busy) return;
    setBusy(type);
    setFeedback(null);
    try {
      const data = await prepareDeclarationDocument(id, type);
      setState({ kind: "ready", data });
      setFeedback({ error: false, text: "报关资料已从 NS 下载并保存到共享盘。" });
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "下载失败，可稍后重试" });
      setRefresh((n) => n + 1);
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

  async function closeLine(lineId: string, body: ClosureRequest) {
    if (busy) return false;
    setBusy(lineId);
    setFeedback(null);
    try {
      setState({ kind: "ready", data: await closeTaskLine(id, lineId, body) });
      setFeedback({ error: false, text: "差异结束决定已登记。" });
      return true;
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "登记失败，请刷新后核实" });
      return false;
    } finally {
      setBusy(null);
    }
  }

  if (state.kind === "loading") return <Skeleton label="正在加载任务" />;
  if (state.kind === "error")
    return (
      <Card>
        <ErrorState
          title="任务暂时无法加载"
          message={state.message}
          action={
            <Button
              onClick={() => {
                setState({ kind: "loading" });
                setRefresh((n) => n + 1);
              }}
            >
              重新加载
            </Button>
          }
        />
      </Card>
    );
  const data = state.data;
  const step = data.steps.find((item) => item.key === section);
  const superseded = data.sourceStatus === "superseded";
  return (
    <div className="it-page itd-page">
      {data.task.predecessorTaskIds?.length > 0 && (
        <p className="itd-predecessors">
          前序任务：
          {data.task.predecessorTaskIds.map((previous) => (
            <Link key={previous} to={`${paths.tasks}/${previous}`}>
              {" "}
              #{previous}{" "}
            </Link>
          ))}
        </p>
      )}
      <TaskOverview detail={data} section={section} onNavigate={navigate} />

      <div className="itd-layout">
        <div className="itd-main">
          <Card className="itd-node" id={`task-${section}`} aria-labelledby="itd-node-title">
            <CardHeader
              title={
                <span id="itd-node-title">
                  <span className="itd-node__tag">{section === current ? "当前节点" : "查看节点"}</span>
                  {step?.label ?? "任务节点"}
                </span>
              }
              description={section === current ? data.task.reason : step?.description}
              actions={
                section !== current ? (
                  <Button size="sm" onClick={() => navigate(current)}>
                    回到当前节点
                  </Button>
                ) : undefined
              }
            />
            <CardContent>
              {feedback && (
                <p className="itd-feedback" role={feedback.error ? "alert" : "status"}>
                  {feedback.text}
                </p>
              )}
              {section === "review" && (
                <NodeText title="财务审核已通过">
                  <p>
                    报关单：{data.task.recordNumber || "报关单号缺失"} · 审核版本 {data.task.reviewRevision}
                  </p>
                  <p>{data.sourceMessage}</p>
                </NodeText>
              )}
              {section === "documents" && (
                <TaskDocuments
                  detail={data}
                  busy={busy}
                  onPrepare={(orderId) => void prepare(orderId)}
                  onRetryDeclaration={(type) => void retryDeclaration(type)}
                  onUploadSigned={() => setUploading(true)}
                  onNotify={() => navigate("notification")}
                />
              )}
              {/* 通知组件常驻，保留企微发送状态的轮询；只在通知节点显示 */}
              <div hidden={section !== "notification"}>
                <TaskNotification
                  key={`${data.task.id}:${data.notification.revision}:${data.task.status}`}
                  detail={data}
                  onSave={saveNotification}
                  onRecord={recordNotification}
                  delivery={delivery}
                />
              </div>
              {section === "invoices" && (
                <NodeText title={data.notification.statusLabel}>
                  <p>
                    已收数量与含税金额由发票比对中已通过的分配汇总，不能手工修改；收票进度见下方应开明细。
                  </p>
                  <dl className="itd-facts itd-facts--inline">
                    <div>
                      <dt>跟进人</dt>
                      <dd>{data.task.followupEmployee || "未指定"}</dd>
                    </div>
                    <div>
                      <dt>最近联系（北京时间）</dt>
                      <dd>{data.task.lastContactAt ? formatTime(data.task.lastContactAt) : "暂无记录"}</dd>
                    </div>
                  </dl>
                  <Button onClick={() => navigate("notification")}>查看通知与催票</Button>
                </NodeText>
              )}
              {section === "comparison" && (
                <NodeText title="发票比对">
                  <p>{data.compare.reason}</p>
                  <Link className="ui-button ui-button--secondary" to={paths.matching}>
                    前往发票比对
                  </Link>
                </NodeText>
              )}
              {section === "completion" && (
                <div className="itd-content">
                  <NodeText title={data.task.status === "completed" ? "任务已完成" : "补齐完结资料"}>
                    <p>
                      发票全部收齐（或按当前依据人工登记差异结束）且资料全部到齐后，任务自动完成。
                      {data.completion ? `资料情况：${data.completion.reason}。` : ""}
                    </p>
                  </NodeText>
                  <DeclarationDocuments
                    documents={data.declarationDocuments}
                    busy={busy}
                    onRetry={(type) => void retryDeclaration(type)}
                  />
                  <SignedContracts
                    contracts={data.signedContracts}
                    disabled={superseded || busy !== null}
                    onUpload={() => setUploading(true)}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          <Card aria-labelledby="itd-lines-title">
            <CardHeader
              title={<span id="itd-lines-title">应开明细与收票进度</span>}
              description="按财务审核时冻结的数量和金额跟进；已收由比对通过的发票自动汇总"
            />
            <CardContent>
              <TaskLines lines={data.lines} busy={!!busy} open onClose={closeLine} />
            </CardContent>
          </Card>
        </div>

        <aside className="itd-aside" aria-label="资料与记录">
          <Card aria-labelledby="itd-docs-title">
            <CardHeader
              title={<span id="itd-docs-title">完结资料</span>}
              description={
                data.completion?.ready ? "资料已全部到齐" : "子采购合同、报关单、销售合同、发票、回签合同"
              }
            />
            <CardContent>
              {data.completion ? (
                data.completion.missing.length ? (
                  <ul className="itd-missing">
                    {data.completion.missing.map((name) => (
                      <li key={name}>
                        <span aria-hidden="true">!</span>
                        尚缺：{name}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="itd-ready">✓ 资料已全部到齐</p>
                )
              ) : (
                <p className="it-help">资料情况待获取</p>
              )}
              <div className="itd-aside__actions">
                <Button size="sm" onClick={() => navigate("documents")}>
                  查看合同与资料
                </Button>
                <Button size="sm" disabled={superseded} onClick={() => setUploading(true)}>
                  上传回签合同
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card aria-labelledby="itd-history-title">
            <CardHeader title={<span id="itd-history-title">流转记录</span>} />
            <CardContent>
              <TaskHistory detail={data} />
            </CardContent>
          </Card>
          <Card aria-labelledby="itd-info-title">
            <CardHeader title={<span id="itd-info-title">任务信息</span>} />
            <CardContent>
              <dl className="itd-facts">
                <div>
                  <dt>审核来源环境</dt>
                  <dd>{data.task.account}</dd>
                </div>
                <div>
                  <dt>原件下载环境</dt>
                  <dd>{data.downloadEnvironment || "未配置"}</dd>
                </div>
                <div>
                  <dt>任务生成时间（北京时间）</dt>
                  <dd>{formatTime(data.task.createdAt)}</dd>
                </div>
                <div>
                  <dt>依据说明</dt>
                  <dd>{data.sourceMessage}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </aside>
      </div>

      {uploading && (
        <SignedContractUpload
          onClose={(changed) => {
            setUploading(false);
            if (changed) setRefresh((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

function NodeText({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="itd-node-text">
      <h3>{title}</h3>
      {children}
    </div>
  );
}
