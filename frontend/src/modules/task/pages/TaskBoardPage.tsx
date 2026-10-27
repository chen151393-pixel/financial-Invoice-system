import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { paths } from "../../../app/paths";
import {
  Alert,
  Button,
  Card,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import { queryTaskBoard } from "../api/board";
import { BoardNodeCards } from "../components/BoardNodeCards";
import { BoardTaskItem } from "../components/BoardTaskItem";
import { SignedContractUpload } from "../components/SignedContractUpload";
import type { BoardNodeKey, TaskBoard, TaskBoardQuery } from "../types/board";
import { stageLabels } from "../types/task";
import "./task-board.css";

const NODE_KEYS: readonly BoardNodeKey[] = [
  "documents",
  "notification",
  "invoices",
  "comparison",
  "completion",
  "done",
];
type Remote = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: TaskBoard };

function readNode(value: string | null): TaskBoardQuery["node"] {
  return NODE_KEYS.find((key) => key === value) ?? "";
}

/** 开票跟进：节点卡片筛选，列表卡片内含查询栏与任务卡片；单项处理进入详情，回签合同支持批量上传。 */
export function TaskBoardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState<TaskBoardQuery>({
    keyword: "",
    supplierId: searchParams.get("supplierId") || "",
    ...(searchParams.has("stage") ? { stage: searchParams.get("stage") || "" } : {}),
    ...(searchParams.has("createdFrom") ? { createdFrom: searchParams.get("createdFrom") || "" } : {}),
    ...(searchParams.has("createdTo") ? { createdTo: searchParams.get("createdTo") || "" } : {}),
    node: readNode(searchParams.get("node")),
    page: 1,
    pageSize: 20,
  });
  const [keyword, setKeyword] = useState("");
  const [supplierId, setSupplierId] = useState(query.supplierId);
  const [state, setState] = useState<Remote>({ kind: "loading" });
  // 最近一次成功结果的分区与供应商选项；重新查询时保留，避免分区闪烁
  const [last, setLast] = useState<TaskBoard | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await queryTaskBoard(query);
        if (!active) return;
        setState({ kind: "ready", data });
        setLast(data);
      } catch (error) {
        if (active)
          setState({
            kind: "error",
            message: error instanceof Error ? error.message : "开票任务加载失败",
          });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);

  function change(patch: Partial<TaskBoardQuery>) {
    setState({ kind: "loading" });
    const next = { ...query, page: 1, ...patch };
    setQuery(next);
    // 节点与供应商写入地址，刷新或分享链接后保持同一视图
    const params = new URLSearchParams();
    if (next.node) params.set("node", next.node);
    if (next.supplierId) params.set("supplierId", next.supplierId);
    if (next.stage) params.set("stage", next.stage);
    if (next.createdFrom) params.set("createdFrom", next.createdFrom);
    if (next.createdTo) params.set("createdTo", next.createdTo);
    setSearchParams(params, { replace: true });
  }
  function reload() {
    setState({ kind: "loading" });
    setRefresh((n) => n + 1);
  }
  function showAll() {
    setKeyword("");
    setSupplierId("");
    change({ keyword: "", supplierId: "", node: "", stage: "", createdFrom: "", createdTo: "" });
  }

  const busy = state.kind === "loading";
  const board = state.kind === "ready" ? state.data : last;
  const nodeLabel = query.node
    ? (board?.nodes.find((node) => node.key === query.node)?.label ?? "任务")
    : query.stage
      ? "当前业务状态的任务"
      : "全部进行中";
  const scoped = Boolean(query.stage || query.createdFrom || query.createdTo);
  const filtered = Boolean(query.keyword || query.supplierId || scoped);
  const edited = keyword !== query.keyword || supplierId !== query.supplierId;

  return (
    <div className="tb">
      {board ? (
        <BoardNodeCards
          nodes={board.nodes}
          openTotal={board.openTotal}
          value={query.node}
          showOpenTotal={!query.stage}
          onChange={(node) => !busy && change({ node })}
        />
      ) : (
        state.kind === "loading" && <Skeleton rows={1} label="正在汇总任务节点" />
      )}

      <Card className="tb-panel">
        <CardHeader
          title={<span id="tb-list-title">{nodeLabel}</span>}
          description={
            state.kind === "ready"
              ? `共 ${state.data.total} 个任务 · ${query.node === "done" ? "最新完成的在前" : "等待最久的在前"}`
              : undefined
          }
          actions={
            <Button disabled={busy} onClick={() => setUploading(true)}>
              批量上传回签合同
            </Button>
          }
        />
        <FilterBar
          embedded
          onSubmit={() => change({ keyword, supplierId })}
          pending={edited ? "条件已修改，点击「查询」生效" : undefined}
          actions={
            <>
              <Button variant="primary" type="submit" disabled={busy}>
                {busy ? "查询中…" : "查询"}
              </Button>
              <Button
                disabled={busy || (!filtered && !keyword && !supplierId)}
                onClick={() => {
                  setKeyword("");
                  setSupplierId("");
                  change({ keyword: "", supplierId: "", stage: "", createdFrom: "", createdTo: "" });
                }}
              >
                清除
              </Button>
              <Button disabled={busy} onClick={reload}>
                刷新
              </Button>
            </>
          }
        >
          <Field label="报关单 / 供应商 / 子采购单" grow>
            <input
              type="search"
              maxLength={120}
              placeholder="CD 编号、供应商名称或子采购单号"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
          </Field>
          <Field label="供应商">
            <select value={supplierId} onChange={(event) => setSupplierId(event.target.value)}>
              <option value="">全部供应商</option>
              {(board?.suppliers ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
        </FilterBar>

        {scoped && (
          <div className="tb-scope">
            <Alert tone="info" title="已应用报关单范围">
              {query.stage && (
                <span>
                  业务状态：
                  {Object.entries(stageLabels).find(([key]) => key === query.stage)?.[1] ?? query.stage}
                  。{" "}
                </span>
              )}
              {(query.createdFrom || query.createdTo) && (
                <span>
                  创建日期：{query.createdFrom || "未填写"} 至 {query.createdTo || "未填写"}。{" "}
                </span>
              )}
              <Button
                size="sm"
                onClick={() => change({ stage: "", createdFrom: "", createdTo: "", node: "" })}
              >
                清除范围
              </Button>
            </Alert>
          </div>
        )}

        {uploading && (
          <SignedContractUpload
            onClose={(changed) => {
              setUploading(false);
              if (changed) reload();
            }}
          />
        )}
        <section className="tb-list" aria-labelledby="tb-list-title">
          {state.kind === "loading" && <Skeleton label="正在读取开票任务" />}

          {state.kind === "error" && (
            <ErrorState
              title="开票任务暂时无法加载"
              message={state.message}
              action={<Button onClick={reload}>重新加载</Button>}
            />
          )}

          {state.kind === "ready" &&
            (state.data.items.length ? (
              state.data.items.map((item) => <BoardTaskItem key={item.task.id} item={item} />)
            ) : (
              <EmptyState
                title={
                  filtered
                    ? "当前条件下没有任务"
                    : query.node
                      ? `没有处于「${nodeLabel}」的任务`
                      : "还没有进行中的开票任务"
                }
                description={
                  filtered || query.node
                    ? "可切换节点或清除搜索条件查看其他任务。"
                    : "财务审核通过后按供应商、采购公司和币种自动生成开票任务。"
                }
                action={
                  filtered || query.node ? (
                    <Button onClick={showAll}>查看全部进行中</Button>
                  ) : (
                    <Link className="ui-button ui-button--secondary" to={paths.review}>
                      前往财务核对
                    </Link>
                  )
                }
              />
            ))}
        </section>

        {state.kind === "ready" && state.data.total > 0 && (
          <CardFooter>
            <Pagination
              label="开票任务分页"
              total={state.data.total}
              page={state.data.page}
              pageCount={state.data.pages}
              pageSize={state.data.pageSize}
              pageSizes={[10, 20, 50]}
              onPageChange={(page) => change({ page })}
              onPageSizeChange={(pageSize) => change({ pageSize })}
            />
          </CardFooter>
        )}
      </Card>

      <details className="tb-definitions">
        <summary>节点口径</summary>
        <p>
          六个节点与任务详情页一致，各按自身事实判断：资料准备看子采购合同是否全部保存到共享盘；通知供应商看最新通知是否已发送（人工登记或企微确认）；等待收票看是否收到发票；发票比对看全部任务行是否已结束；完成要求发票收齐且子采购合同、报关单、销售合同、发票、回签合同全部到齐。
        </p>
        <p>
          任务按“第一个未完成的节点”归入分区；发票可能先于合同或通知到达，此时停在较早的节点。分区计数覆盖全部筛选结果，不只本页。来源或开票依据变化的任务显示“暂不能推进”，需财务重新审核。查询和切换节点不会触发下载、通知或
          NS 写入。
        </p>
      </details>
    </div>
  );
}
