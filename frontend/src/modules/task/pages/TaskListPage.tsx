import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Button,
  Card,
  CardFooter,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  SectionTitle,
  Skeleton,
} from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import { listTasks, uploadSignedContracts } from "../api/task";
import { SignedContractUpload } from "../components/SignedContractUpload";
import { TaskCountList } from "../components/TaskCountList";
import { TaskFollowupTable } from "../components/TaskFollowupTable";
import { TaskListToolbar } from "../components/TaskListToolbar";
import { stageLabels, type TaskList, type TaskListQuery, type TaskStage } from "../types/task";
import "./task.css";

type Remote<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

function initialStage(value: string | null): TaskStage {
  return value && Object.hasOwn(stageLabels, value) ? (value as TaskStage) : "";
}

export function TaskListPage() {
  // 工作台业务状态分区跳转时带入筛选条件
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState<TaskListQuery>({
    keyword: "",
    supplierId: searchParams.get("supplierId") || "",
    stage: initialStage(searchParams.get("stage")),
    createdFrom: searchParams.get("createdFrom") || "",
    createdTo: searchParams.get("createdTo") || "",
    groupBy: "supplier",
    status: "current",
    page: 1,
    pageSize: 20,
  });
  const [keyword, setKeyword] = useState("");
  const [supplierId, setSupplierId] = useState(query.supplierId);
  const [stage, setStage] = useState<TaskStage>(query.stage);
  const [createdFrom, setCreatedFrom] = useState(query.createdFrom);
  const [createdTo, setCreatedTo] = useState(query.createdTo);
  const [suppliers, setSuppliers] = useState<TaskList["suppliers"]>([]);
  const [state, setState] = useState<Remote<TaskList>>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [uploading, setUploading] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await listTasks(query);
        if (active) {
          setState({ kind: "ready", data });
          setSuppliers(data.suppliers ?? []);
        }
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "开票任务加载失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);
  function change(patch: Partial<TaskListQuery>) {
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  }
  const busy = state.kind === "loading";
  const edited =
    keyword !== query.keyword ||
    supplierId !== query.supplierId ||
    stage !== query.stage ||
    createdFrom !== query.createdFrom ||
    createdTo !== query.createdTo;
  const filtered = Boolean(
    query.keyword || query.supplierId || query.stage || query.createdFrom || query.status !== "current",
  );
  function reload() {
    setState({ kind: "loading" });
    setRefresh((n) => n + 1);
  }
  return (
    <div className="it-page">
      <FilterBar
        onSubmit={() => change({ keyword, supplierId, stage, createdFrom, createdTo })}
        pending={edited ? "条件已修改，点击「查询」生效；当前结果仍使用上次提交的条件" : undefined}
        actions={
          <>
            <Button variant="primary" type="submit" disabled={busy}>
              {busy ? "查询中…" : "查询"}
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
            placeholder="输入编号或名称"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </Field>
        <Field label="供应商">
          <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
            <option value="">全部供应商</option>
            {suppliers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="业务状态">
          <select value={stage} onChange={(e) => setStage(initialStage(e.target.value))}>
            <option value="">全部状态</option>
            {Object.entries(stageLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="报关单创建日期 从">
          <input type="date" value={createdFrom} onChange={(e) => setCreatedFrom(e.target.value)} />
        </Field>
        <Field label="至">
          <input type="date" value={createdTo} onChange={(e) => setCreatedTo(e.target.value)} />
        </Field>
      </FilterBar>
      {uploading && (
        <SignedContractUpload
          upload={uploadSignedContracts}
          onClose={(changed) => {
            setUploading(false);
            if (changed) {
              setState({ kind: "loading" });
              setRefresh((n) => n + 1);
            }
          }}
        />
      )}
      <SectionTitle
        title="开票任务"
        count={
          state.kind === "ready"
            ? `共 ${state.data.counts.tasks} 个任务 · ${state.data.total} 个${
                query.groupBy === "supplier" ? "供应商分组" : "报关单分组"
              }`
            : undefined
        }
        actions={
          <>
            {state.kind === "ready" && <TaskCountList counts={state.data.counts} />}
            <Button disabled={busy} onClick={() => setUploading(true)}>
              批量上传回签合同
            </Button>
          </>
        }
      />
      <TaskListToolbar
        query={query}
        supplierName={suppliers.find((item) => item.id === query.supplierId)?.name}
        busy={busy}
        onChange={change}
        onClear={(filter) => {
          if (filter === "all") {
            setKeyword("");
            setSupplierId("");
            setStage("");
            setCreatedFrom("");
            setCreatedTo("");
            change({
              keyword: "",
              supplierId: "",
              stage: "",
              createdFrom: "",
              createdTo: "",
              status: "current",
            });
          } else if (filter === "keyword") {
            setKeyword("");
            change({ keyword: "" });
          } else if (filter === "supplier") {
            setSupplierId("");
            change({ supplierId: "" });
          } else if (filter === "stage") {
            setStage("");
            change({ stage: "" });
          } else if (filter === "created") {
            setCreatedFrom("");
            setCreatedTo("");
            change({ createdFrom: "", createdTo: "" });
          } else {
            change({ status: "current" });
          }
        }}
      />
      {state.kind === "loading" && <Skeleton label="正在读取开票任务" />}
      {state.kind === "error" && (
        <Card>
          <ErrorState
            title="开票任务暂时无法加载"
            message={state.message}
            action={<Button onClick={reload}>重新加载</Button>}
          />
        </Card>
      )}
      {state.kind === "ready" && (
        <Card>
          {state.data.groups.length ? (
            <TaskFollowupTable groups={state.data.groups} groupBy={state.data.groupBy} />
          ) : (
            <EmptyState
              title={filtered ? "没有符合条件的任务" : "还没有开票任务"}
              description="财务审核通过后按供应商、采购公司和币种自动生成任务；新链路之前的旧任务不迁移。"
              action={
                <Link className="ui-button ui-button--secondary" to={paths.review}>
                  前往财务核对
                </Link>
              }
            />
          )}
          <CardFooter>
            <Pagination
              label="开票任务分组分页"
              total={state.data.total}
              page={state.data.page}
              pageCount={state.data.pages}
              pageSize={state.data.pageSize}
              pageSizes={[10, 20, 50]}
              onPageChange={(page) => change({ page })}
              onPageSizeChange={(pageSize) => change({ pageSize })}
            />
          </CardFooter>
        </Card>
      )}
    </div>
  );
}
