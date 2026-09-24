import { useEffect, useRef, useState } from "react";
import { AppFrame } from "../../../web/shared/components/AppFrame";
import { Button } from "../../../web/shared/components/Button";
import { navigation } from "../../../web/app/navigation";
import { viewPath } from "../../../web/app/views";
import {
  followupTasks,
  stages,
  groupFollowupTasks,
  type FollowupTask,
  type FollowupGroupBy,
} from "../invoice-followup-data";
import "./invoice-followup.css";
import { SupplierNotification } from "./SupplierNotification";
import {
  demoSupplierContact,
  notificationScenes,
  type NotificationScene,
  type ManualNotificationRecord,
} from "../supplier-notification-data";

type Tab = "review" | "notification" | "documents" | "invoices" | "comparison" | "completion" | "history";
const stageTabs: Tab[] = ["review", "documents", "notification", "invoices", "comparison", "completion"];
type Filter = "all" | "mine" | "supplier" | "done";
type Preview = { title: string; content: string };

function Icon({ name }: { name: "arrow" | "check" | "clock" | "alert" | "file" | "search" | "chevron" }) {
  const paths = {
    arrow: "M5 12h14m-5-5 5 5-5 5",
    check: "m5 12 4 4L19 6",
    clock: "M12 8v4l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    alert: "M12 8v5m0 3v.1M12 3 2 21h20L12 3Z",
    file: "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6",
    search: "m16 16 4 4M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    chevron: "m9 5 7 7-7 7",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

function Status({ task }: { task: FollowupTask }) {
  return (
    <span className={`if-status if-status--${task.tone}`}>
      <Icon name={task.tone === "done" ? "check" : task.tone === "attention" ? "alert" : "clock"} />
      {task.status}
    </span>
  );
}

function PreviewDialog({ preview, close }: { preview: Preview; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);
  return (
    <dialog ref={ref} className="if-dialog" onCancel={close} aria-labelledby="if-preview-title">
      <header>
        <h2 id="if-preview-title">{preview.title}</h2>
        <Button onClick={close}>关闭</Button>
      </header>
      <p className="if-demo-note">内容预览 · 演示数据，不会发送给供应商</p>
      <pre>{preview.content}</pre>
      <footer>
        <span>仅供预览，不执行真实发送。</span>
        <Button variant="primary" onClick={close}>
          返回示例
        </Button>
      </footer>
    </dialog>
  );
}

function TaskDetail({
  task: baseTask,
  back,
  showPreview,
}: {
  task: FollowupTask;
  back: () => void;
  showPreview: (value: Preview) => void;
}) {
  const params = new URLSearchParams(location.search);
  const notificationEntry = params.get("tab") === "notification" && params.get("task") === baseTask.id;
  const [tab, setTab] = useState<Tab>(notificationEntry ? "notification" : "documents");
  const [notificationScene, setNotificationScene] = useState<NotificationScene | null>(() =>
    notificationEntry ? "missing" : null,
  );
  const [contact, setContact] = useState(() => ({
    ...demoSupplierContact,
    groupName: `${baseTask.supplier}开票对接群（示例）`,
  }));
  const [manualRecord, setManualRecord] = useState<ManualNotificationRecord | null>(null);
  const [notificationMessage, setNotificationMessage] = useState<string | null>(null);
  const notified = notificationScene === "sent" || notificationScene === "recorded";
  const scene = notificationScene ? notificationScenes[notificationScene] : null;
  const task: FollowupTask = scene
    ? {
        ...baseTask,
        stage: notified ? 3 : 2,
        status: notified ? "等待供应商开票" : scene.label,
        tone: scene.tone,
        description: scene.description,
        next: scene.next,
        action: "查看供应商通知",
        owner: notified ? "供应商" : notificationScene === "pending" ? contact.owner : "采购 / 财务",
        elapsed: "通知场景预览",
        documentsReady: true,
        notification: `${scene.label}（示例）`,
        received: "¥0.00",
        confirmed: "¥0.00",
        invoiceCount: "尚未收票",
        comparisonProgress: undefined,
        history: [
          { time: "09-24 15:30", title: `通知状态：${scene.label}（示例）`, detail: scene.description },
          {
            time: "09-24 15:28",
            title: "合同已保存到共享盘（示例）",
            detail: "按下载日期归档，等待通知供应商。",
          },
          { time: "09-24 15:25", title: "财务审核通过（示例）", detail: "生成开票任务。" },
        ],
      }
    : baseTask;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const notificationContent = `致：${task.supplier}\n\n请按已确认的本次开票范围开具并提交发票。\n\n任务编号：${task.id}\n关联报关单：${task.declaration}\n子采购单：${task.purchase}\n本次应收票金额：${task.total}（人民币）\n约定开票日期：${task.due}\n\n请在发票备注中注明子采购单号，并按本次资料清单核对品名、单位及数量。\n如已开票，请提供发票及对应采购单信息。\n\n此处为通知内容示例，不会实际发送。`;
  const openNotification = () =>
    showPreview({
      title: task.id.endsWith("001") ? "催票通知预览" : "开票通知预览",
      content: notificationContent,
    });
  const openStage = (target: Tab) => {
    setTab(target);
    requestAnimationFrame(() => {
      document.getElementById("if-task-content")?.scrollIntoView({ block: "start" });
      document.getElementById("if-task-content")?.focus({ preventScroll: true });
    });
  };
  const primaryAction = () => {
    if (notificationScene) {
      openStage("notification");
      return;
    }
    if (task.stage === 4 || task.stage === 5) setTab("comparison");
    else if (task.id.endsWith("002")) setTab("invoices");
    else if (task.stage === 1 || task.stage === 2) setTab("history");
    else openNotification();
  };
  const tabs: { id: Tab; label: string }[] = [
    { id: "review", label: "财务审核" },
    { id: "documents", label: "开票资料" },
    { id: "notification", label: "供应商通知" },
    { id: "invoices", label: "收票进度" },
    { id: "comparison", label: "比对结果" },
    { id: "completion", label: "完成情况" },
    { id: "history", label: "操作记录" },
  ];
  return (
    <>
      <button className="if-back" onClick={back}>
        ← 返回全部任务
      </button>
      <section className="if-detail">
        <header className="if-detail-heading">
          <div>
            <h2 ref={heading} tabIndex={-1}>
              {task.supplier}
            </h2>
            <p>
              {task.id} <span>／</span> {task.declaration} <span>／</span> 示例采购公司
            </p>
          </div>
          <Status task={task} />
        </header>
        <ol className="if-steps" aria-label="开票流程节点">
          {stages.map((stage, index) => (
            <li
              key={stage}
              className={
                index < task.stage || task.stage === 5
                  ? "is-complete"
                  : index === task.stage
                    ? `is-current ${task.tone === "attention" ? "is-attention" : ""}`
                    : index === 4 && task.comparisonProgress
                      ? "is-partial"
                      : ""
              }
              aria-current={index === task.stage ? "step" : undefined}
            >
              <button
                type="button"
                className="if-step-button"
                aria-label={`查看${stage}节点`}
                aria-pressed={tab === stageTabs[index]}
                aria-controls="if-task-content"
                onClick={() => openStage(stageTabs[index])}
              >
                <span className="if-step-dot">
                  {index < task.stage || task.stage === 5 ? <Icon name="check" /> : index + 1}
                </span>
                <strong>{stage}</strong>
                <small>
                  {index < task.stage || task.stage === 5
                    ? "已完成"
                    : index === task.stage
                      ? "当前节点"
                      : index === 4 && task.comparisonProgress
                        ? task.comparisonProgress
                        : "待开始"}
                </small>
              </button>
            </li>
          ))}
        </ol>
        <div className={`if-current if-current--${task.tone}`}>
          <div className="if-current-icon">
            <Icon name={task.tone === "attention" ? "alert" : task.tone === "done" ? "check" : "clock"} />
          </div>
          <div>
            <h3>
              {task.status}
              <span>{task.elapsed}</span>
            </h3>
            <p>{task.description}</p>
            <p>{task.next}</p>
          </div>
          <Button variant="primary" onClick={primaryAction}>
            {task.action}
          </Button>
        </div>
        <dl className="if-amounts">
          <div>
            <dt>本次应收票</dt>
            <dd>{task.total}</dd>
          </div>
          <div>
            <dt>已收到发票</dt>
            <dd>{task.received}</dd>
          </div>
          <div>
            <dt>已确认匹配</dt>
            <dd>{task.confirmed}</dd>
          </div>
          <div>
            <dt>{task.stage === 5 ? "完成人" : "当前等待"}</dt>
            <dd className="if-owner">{task.owner}</dd>
          </div>
        </dl>
        <div className="if-detail-body">
          <div className="if-tab-buttons" role="group" aria-label="任务详情内容">
            {tabs.map((item) => (
              <button key={item.id} aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>
                {item.label}
              </button>
            ))}
          </div>
          <section
            id="if-task-content"
            tabIndex={-1}
            className="if-tab-content"
            aria-label={tabs.find((item) => item.id === tab)?.label}
          >
            {tab === "completion" && (
              <>
                <div className="if-section-heading">
                  <div>
                    <h3>{task.stage === 5 ? "本次开票任务已完成" : "本次开票任务尚未完成"}</h3>
                    <p>
                      {task.stage === 5
                        ? "发票已收齐并确认匹配；本流程完成不代表已付款或已回写 NS。"
                        : `当前进度：${stages[task.stage]}。${task.next}`}
                    </p>
                  </div>
                  <span>完成情况 · 示例</span>
                </div>
                <div className="if-document">
                  <Icon name={task.stage === 5 ? "check" : "clock"} />
                  <div>
                    <strong>
                      {task.id} · {task.supplier}
                    </strong>
                    <p>
                      本次应收票 {task.total} · 已收票 {task.received} · 已确认匹配 {task.confirmed}
                    </p>
                  </div>
                  <Button onClick={() => setTab(task.stage === 5 ? "history" : stageTabs[task.stage])}>
                    {task.stage === 5 ? "查看完整记录" : "查看当前节点"}
                  </Button>
                </div>
              </>
            )}
            {tab === "notification" && !task.documentsReady && (
              <div className="if-empty">
                <h3>等待合同保存到共享盘</h3>
                <p>当前文件获取失败，通知尚未开始。请在操作记录中查看原因。</p>
                <Button onClick={() => setTab("history")}>查看操作记录</Button>
              </div>
            )}
            {tab === "notification" && task.documentsReady && (
              <SupplierNotification
                task={task}
                scene={notificationScene ?? (baseTask.stage >= 3 ? "sent" : "unknown")}
                onScene={setNotificationScene}
                contact={contact}
                onContact={setContact}
                manualRecord={manualRecord}
                onManualRecord={setManualRecord}
                messageDraft={notificationMessage}
                onMessageChange={setNotificationMessage}
                preview={showPreview}
              />
            )}
            {tab === "documents" && (
              <>
                <div className="if-section-heading">
                  <div>
                    <h3>本次开票资料</h3>
                    <p>以审核确认的范围为准，子采购单原始金额不自动作为开票额度。</p>
                  </div>
                  <span>版本 V1 · 示例</span>
                </div>
                <div className="if-document">
                  <Icon name="file" />
                  <div>
                    <strong>子采购单与开票清单</strong>
                    <p>
                      {task.purchase} ·{" "}
                      {task.documentsReady ? "已保存，包含本次开票范围" : "文件获取失败，等待处理"}
                    </p>
                  </div>
                  <span className="if-date">{task.documentsReady ? "已保存至共享盘（示例）" : "待保存"}</span>
                </div>
                <div className="if-notification">
                  <div>
                    <h3>供应商通知</h3>
                    <p>{task.notification}</p>
                  </div>
                  {task.stage >= 2 && <Button onClick={() => setTab("notification")}>查看供应商通知</Button>}
                </div>
                {!task.documentsReady && (
                  <p className="if-warning">资料尚未齐备，通知已暂停。请在操作记录中查看失败原因。</p>
                )}
                {task.stage === 2 && (!notificationScene || notificationScene === "unknown") && (
                  <p className="if-warning">发送结果尚未确认，不提供再次发送操作。请先核实原通知。</p>
                )}
              </>
            )}
            {tab === "invoices" && (
              <>
                <div className="if-section-heading">
                  <div>
                    <h3>{task.invoiceCount}</h3>
                    <p>已收票与已确认匹配分别展示；部分收票可先行比对。</p>
                  </div>
                </div>
                {task.received === "¥0.00" ? (
                  <div className="if-empty">
                    <Icon name="file" />
                    <h3>暂未收到发票</h3>
                    <p>
                      {task.stage < 3
                        ? "先完成资料准备与供应商通知。"
                        : `约定开票日期 ${task.due}，收到发票后进入比对。`}
                    </p>
                    <Button disabled>接收发票（未接入）</Button>
                  </div>
                ) : (
                  <div className="if-table-scroll">
                    <table className="if-table">
                      <thead>
                        <tr>
                          <th>示例发票编号</th>
                          <th>含税金额</th>
                          <th>比对状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {task.id.endsWith("002") ? (
                          <>
                            <tr>
                              <td>INV-DEMO-002-A</td>
                              <td>¥40,000.00</td>
                              <td>已确认</td>
                            </tr>
                            <tr>
                              <td>INV-DEMO-002-B</td>
                              <td>¥20,000.00</td>
                              <td>待比对</td>
                            </tr>
                          </>
                        ) : (
                          <tr>
                            <td>INV-DEMO-{task.id.slice(-3)}</td>
                            <td>{task.received}</td>
                            <td>{task.stage === 5 ? "已确认" : "存在金额差异"}</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
            {tab === "comparison" && (
              <>
                <div className="if-section-heading">
                  <div>
                    <h3>
                      {task.stage === 4
                        ? "1 项差异需要核实"
                        : task.stage === 5
                          ? "本次匹配已确认"
                          : "比对进度"}
                    </h3>
                    <p>比较发票与本次采购依据，保留原始值和确认记录。</p>
                  </div>
                </div>
                {task.stage >= 4 ? (
                  <>
                    <div className="if-table-scroll">
                      <table className="if-table">
                        <thead>
                          <tr>
                            <th>比对项目</th>
                            <th>本次采购依据</th>
                            <th>发票信息</th>
                            <th>结果</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>供应商</td>
                            <td>{task.supplier}</td>
                            <td>{task.supplier}</td>
                            <td>一致</td>
                          </tr>
                          <tr>
                            <td>采购公司／币种</td>
                            <td>示例采购公司／人民币</td>
                            <td>示例采购公司／人民币</td>
                            <td>一致</td>
                          </tr>
                          <tr>
                            <td>商品／数量／单位</td>
                            <td>示例标准件／100／件</td>
                            <td>示例标准件／100／件</td>
                            <td>一致</td>
                          </tr>
                          <tr className={task.stage === 4 ? "if-difference" : ""}>
                            <td>含税金额</td>
                            <td>{task.total}</td>
                            <td>{task.received}</td>
                            <td>{task.stage === 4 ? "+¥200.00 · 待核实" : "一致"}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    <p className="if-warning">
                      {task.stage === 4
                        ? "金额差异尚未解决，不能确认匹配。此处为固定差异示例。"
                        : "示例确认记录：林晓 · 2026-09-24 10:18。未执行付款或 NS 回写。"}
                    </p>
                  </>
                ) : (
                  <div className="if-empty">
                    <Icon name="search" />
                    <h3>{task.id.endsWith("002") ? "首批已确认，剩余发票待比对" : "等待发票进入比对"}</h3>
                    <p>
                      {task.id.endsWith("002")
                        ? "已确认 ¥40,000.00；另有 ¥20,000.00 发票待比对，剩余开票范围继续收票。"
                        : "收到发票后，展示供应商、品名、数量、单位及金额的逐项结果。"}
                    </p>
                  </div>
                )}
              </>
            )}
            {(tab === "history" || tab === "review") && (
              <>
                <div className="if-section-heading">
                  <div>
                    <h3>{tab === "review" ? "财务审核已通过" : "流程操作记录"}</h3>
                    <p>
                      {tab === "review"
                        ? `关联报关单 ${task.declaration}，子采购订单 ${task.purchase}；审核通过后生成本次开票任务。以下为示例审核记录。`
                        : "最新记录在前，保留已完成节点与异常原因。以下时间均为示例。"}
                    </p>
                  </div>
                </div>
                <ol className="if-history">
                  {task.history
                    .filter((event) => tab !== "review" || event.title.includes("审核"))
                    .map((event) => (
                      <li key={event.time}>
                        <time>{event.time}</time>
                        <div>
                          <strong>{event.title}</strong>
                          <p>{event.detail}</p>
                        </div>
                      </li>
                    ))}
                </ol>
              </>
            )}
          </section>
        </div>
      </section>
    </>
  );
}

export default function InvoiceFollowup() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<FollowupTask | null>(() => {
    const taskId = new URLSearchParams(location.search).get("task");
    return followupTasks.find((task) => task.id === taskId) ?? null;
  });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [scene, setScene] = useState("normal");
  const [groupBy, setGroupBy] = useState<FollowupGroupBy>("supplier");
  const [expanded, setExpanded] = useState<Record<FollowupGroupBy, string[]>>({
    supplier: ["宁波海川五金有限公司"],
    declaration: ["CD-2609018"],
  });
  const lastTrigger = useRef<HTMLButtonElement | null>(null);
  const lastTaskId = useRef<string | null>(null);
  const filters: { id: Filter; title: string; subtitle: string }[] = [
    { id: "all", title: "全部任务", subtitle: "查看完整开票进度" },
    { id: "mine", title: "需内部处理", subtitle: "资料、通知与比对异常" },
    { id: "supplier", title: "等待供应商", subtitle: "跟进开票与剩余收票" },
    { id: "done", title: "已完成", subtitle: "全部收票并确认匹配" },
  ];
  // 此搜索只筛选六条演示场景；正式接入时替换为后端查询与计数。
  const rows = followupTasks.filter(
    (task) =>
      (filter === "all" || task.category === filter) &&
      `${task.supplier} ${task.id} ${task.declaration} ${task.purchase}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );
  const back = () => {
    setSelected(null);
    window.requestAnimationFrame(() => lastTrigger.current?.focus());
  };
  const taskGroups = groupFollowupTasks(rows, groupBy);
  const toggleGroup = (key: string) =>
    setExpanded((current) => ({
      ...current,
      [groupBy]: current[groupBy].includes(key)
        ? current[groupBy].filter((value) => value !== key)
        : [...current[groupBy], key],
    }));
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-followup"
      onNavigate={(target) => location.assign(viewPath(target))}
      title="开票跟进"
      subtitle="从财务审核到发票比对，每笔采购都有清楚的下一步。"
      mode="demo"
      dataLabel="交互示例 · 6 条虚构任务"
      notice="演示模式：所有名称、金额和记录均为虚构。可体验筛选、流程详情、供应商通知状态、企微外部群绑定与通知预览；不会读取业务数据、发送通知或写入 NS。"
      actions={
        <a className="ui-button ui-button--secondary if-entry-link" href="/finance-reconciliation">
          返回财务核对
        </a>
      }
    >
      <div className="if-workspace">
        {!selected && (
          <p className="if-footnote">
            <a href="/demo?view=invoice-followup&task=KP-202609-001&tab=notification">
              查看供应商通知页面示例 →
            </a>
          </p>
        )}
        {selected ? (
          <TaskDetail key={selected.id} task={selected} back={back} showPreview={setPreview} />
        ) : (
          <>
            <div className="if-summary" role="group" aria-label="按跟进对象筛选">
              {filters.map((item) => (
                <button key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>
                  <span>
                    {item.title}
                    <strong>
                      {item.id === "all"
                        ? 6
                        : followupTasks.filter((task) => task.category === item.id).length}
                    </strong>
                  </span>
                  <small>{item.subtitle}</small>
                </button>
              ))}
            </div>
            <section className="if-list" aria-label="开票任务列表">
              <div className="if-list-heading">
                <div>
                  <h2>开票任务</h2>
                  <p>同一批任务，两种跟进视角；展开分组查看各任务节点。</p>
                </div>
                <span className="if-date">示例时点 · 2026 年 9 月 24 日</span>
              </div>
              <div className="if-toolbar">
                <label className="if-search">
                  <Icon name="search" />
                  <span className="if-sr-only">搜索供应商、报关单或采购单</span>
                  <input
                    type="search"
                    placeholder="搜索供应商、报关单或采购单"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <label className="if-scene">
                  预览状态
                  <select value={scene} onChange={(event) => setScene(event.target.value)}>
                    <option value="normal">正常数据</option>
                    <option value="loading">加载中</option>
                    <option value="empty">空结果</option>
                    <option value="error">请求失败</option>
                  </select>
                </label>
              </div>
              <div className="if-grouping-bar">
                <div className="if-view-switch" role="group" aria-label="任务分组方式">
                  <button aria-pressed={groupBy === "supplier"} onClick={() => setGroupBy("supplier")}>
                    按供应商
                  </button>
                  <button aria-pressed={groupBy === "declaration"} onClick={() => setGroupBy("declaration")}>
                    按报关单
                  </button>
                </div>
                <div className="if-expand-actions">
                  <button
                    disabled={scene !== "normal" || rows.length === 0}
                    onClick={() =>
                      setExpanded((current) => ({
                        ...current,
                        [groupBy]: taskGroups.map((group) => group.key),
                      }))
                    }
                  >
                    全部展开
                  </button>
                  <button
                    disabled={scene !== "normal" || rows.length === 0}
                    onClick={() => setExpanded((current) => ({ ...current, [groupBy]: [] }))}
                  >
                    全部收起
                  </button>
                </div>
              </div>
              <p className="if-count-note">
                仅汇总当前筛选结果：待开票为未收齐任务数，已收票为发票张数，待处理为异常任务数，三项可重叠。示例均属于同一采购公司、人民币。
              </p>
              {scene === "loading" ? (
                <div className="if-empty" role="status">
                  <Icon name="clock" />
                  <h3>正在读取开票任务…</h3>
                  <p>加载状态示例，可通过“预览状态”切回正常数据。</p>
                </div>
              ) : scene === "error" ? (
                <div className="if-empty" role="alert">
                  <Icon name="alert" />
                  <h3>暂时无法读取任务</h3>
                  <p>请求失败状态示例。筛选条件已保留。</p>
                  <Button onClick={() => setScene("normal")}>恢复正常示例</Button>
                </div>
              ) : scene === "empty" || rows.length === 0 ? (
                <div className="if-empty" role="status">
                  <Icon name="search" />
                  <h3>没有符合条件的任务</h3>
                  <p>尝试其他供应商名称，或清除筛选查看全部示例。</p>
                  <Button
                    onClick={() => {
                      setQuery("");
                      setFilter("all");
                      setScene("normal");
                    }}
                  >
                    清除筛选
                  </Button>
                </div>
              ) : (
                <div className="if-groups">
                  {taskGroups.map((group) => {
                    const open = expanded[groupBy].includes(group.key);
                    const panelId = `if-group-${groupBy}-${group.key}`;
                    return (
                      <section className="if-task-group" key={group.key}>
                        <button
                          className="if-group-heading"
                          aria-expanded={open}
                          aria-controls={panelId}
                          aria-label={`${open ? "收起" : "展开"}${group.key}的任务`}
                          onClick={() => toggleGroup(group.key)}
                        >
                          <span className={`if-group-chevron ${open ? "is-open" : ""}`}>
                            <Icon name="chevron" />
                          </span>
                          <span className="if-group-identity">
                            <strong>{group.key}</strong>
                            <small>
                              {group.relatedCount} {groupBy === "supplier" ? "张报关单" : "家供应商"} ·{" "}
                              {group.tasks.length} 项任务
                            </small>
                          </span>
                          <span className="if-group-metric">
                            <small>待开票</small>
                            <span>
                              <strong>{group.awaitingCount}</strong> 项未收齐
                            </span>
                          </span>
                          <span className="if-group-metric">
                            <small>已收票</small>
                            <span>
                              <strong>{group.receivedCount}</strong> 张发票
                            </span>
                          </span>
                          <span className={`if-group-metric ${group.attentionCount ? "has-attention" : ""}`}>
                            <small>待处理</small>
                            <span>
                              <strong>{group.attentionCount}</strong> 项异常
                            </span>
                          </span>
                          <span className="if-group-action">{open ? "收起任务" : "展开任务"}</span>
                        </button>
                        <div id={panelId} hidden={!open}>
                          <div className="if-table-scroll">
                            <table className="if-table if-task-table">
                              <thead>
                                <tr>
                                  <th>
                                    {groupBy === "supplier" ? "报关单 / 开票任务" : "供应商 / 开票任务"}
                                  </th>
                                  <th>当前节点</th>
                                  <th className="if-numeric">本次应收票</th>
                                  <th>收票进度</th>
                                  <th>等待对象 / 时间</th>
                                  <th>
                                    <span className="if-sr-only">操作</span>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {group.tasks.map((task) => (
                                  <tr key={task.id}>
                                    <td>
                                      <div className="if-supplier">
                                        <div>
                                          <strong>
                                            {groupBy === "supplier" ? task.declaration : task.supplier}
                                          </strong>
                                          <small>{task.id}</small>
                                          <small>子采购单 {task.purchase}</small>
                                        </div>
                                      </div>
                                    </td>
                                    <td>
                                      <Status task={task} />
                                      <small>
                                        {stages[task.stage]} · 节点 {task.stage + 1} / 6
                                      </small>
                                      {task.comparisonProgress && (
                                        <small>发票比对：{task.comparisonProgress}</small>
                                      )}
                                    </td>
                                    <td className="if-numeric">{task.total}</td>
                                    <td>
                                      <strong>{task.received}</strong>
                                      <small>{task.invoiceCount}</small>
                                    </td>
                                    <td>
                                      {task.owner}
                                      <small className={task.tone === "attention" ? "if-attention-text" : ""}>
                                        {task.elapsed}
                                      </small>
                                    </td>
                                    <td>
                                      <button
                                        className="if-detail-link"
                                        ref={(node) => {
                                          if (lastTaskId.current === task.id) lastTrigger.current = node;
                                        }}
                                        aria-label={`查看任务${task.id}流程`}
                                        onClick={(event) => {
                                          lastTaskId.current = task.id;
                                          lastTrigger.current = event.currentTarget;
                                          setSelected(task);
                                        }}
                                      >
                                        查看流程
                                        <Icon name="arrow" />
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}
              <div className="if-list-footer">
                <span role="status">
                  {scene === "normal"
                    ? `展示 ${taskGroups.length} ${groupBy === "supplier" ? "家供应商" : "张报关单"} · ${rows.length} 条演示任务`
                    : "页面状态预览"}
                </span>
                <span>审核通过后，按确认的开票范围推进</span>
              </div>
            </section>
            <p className="if-footnote">
              <Icon name="file" />
              展开供应商或报关单，再点击“查看流程”。切换视图会保留筛选条件，任务与记录不会改变。
            </p>
          </>
        )}
        {preview && <PreviewDialog preview={preview} close={() => setPreview(null)} />}
      </div>
    </AppFrame>
  );
}
