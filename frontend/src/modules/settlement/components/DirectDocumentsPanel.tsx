import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryDirectDocuments } from "../api";
import type { DirectDocumentList, DirectDocumentQuery, DirectDocumentRow } from "../types";
import { BatchDocuments } from "./BatchDocuments";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: DirectDocumentList }
  | { kind: "error"; message: string };

/** 直接收汇按报关单办理资料；所有资料状态、金额及操作权限来自后端。 */
export function DirectDocumentsPanel() {
  const [params, setParams] = useSearchParams();
  const initial: DirectDocumentQuery = {
    keyword: "",
    consignee: params.get("consignee") || "",
    status: "all",
    page: 1,
    pageSize: 20,
  };
  const [query, setQuery] = useState(initial);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const selected = params.get("declarationNo") || "";
  const detail = useRef<HTMLElement>(null);
  const focused = useRef("");
  useEffect(() => {
    if (selected && state.kind === "ready" && focused.current !== selected) {
      detail.current?.scrollIntoView({ block: "start" });
      detail.current?.focus({ preventScroll: true });
      focused.current = selected;
    }
  }, [selected, state.kind]);
  useEffect(() => {
    const controller = new AbortController();
    queryDirectDocuments(query, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setState({ kind: "ready", result });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请重试" });
      });
    return () => controller.abort();
  }, [query, refresh]);

  function updateQuery(next: DirectDocumentQuery) {
    setState({ kind: "loading" });
    setQuery(next);
  }
  function reload() {
    setState({ kind: "loading" });
    setRefresh((n) => n + 1);
  }
  function select(number: string) {
    const values = new URLSearchParams(params);
    if (number) values.set("declarationNo", number);
    else values.delete("declarationNo");
    setParams(values);
  }
  const columns: Column<DirectDocumentRow>[] = [
    {
      key: "number",
      header: "报关单 / 销售订单",
      width: "220px",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{row.declarationNo}</strong>
          <span>{row.recordNo}</span>
          <span>{row.salesOrders.join("、")}</span>
        </div>
      ),
    },
    { key: "customer", header: "境外收货人", render: (row) => row.consignee || "—" },
    { key: "company", header: "出口抬头", render: (row) => row.exportCompany || "—" },
    {
      key: "amount",
      header: "报关金额",
      align: "right",
      render: (row) => (row.amount ? `${row.currency} ${money(row.amount)}` : "—"),
    },
    { key: "bill", header: "提单", render: (row) => row.billLabel },
    { key: "contract", header: "销售合同", render: (row) => row.contractLabel },
    {
      key: "state",
      header: "资料进度",
      render: (row) => (
        <Badge tone={row.status === "complete" ? "success" : "warning"}>{row.statusLabel}</Badge>
      ),
    },
    {
      key: "action",
      header: "操作",
      render: (row) => (
        <div className="settlement-cell">
          <Button size="sm" onClick={() => select(row.declarationNo)}>
            {row.status === "complete" || !row.edit.allowed ? "查看资料" : "办理资料"}
          </Button>
          {!row.edit.allowed && <span>{row.edit.reason}</span>}
        </div>
      ),
    },
  ];
  return (
    <div className="settlement-page">
      <Card>
        <CardHeader
          title="报关资料清单"
          description="按报关单上传提单、生成销售合同；同一报关单多次收汇沿用同一套资料。"
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            updateQuery({
              ...query,
              keyword: String(data.get("keyword") || "").trim(),
              status: String(data.get("status") || "all") as DirectDocumentQuery["status"],
              page: 1,
            });
          }}
          actions={
            <>
              <Button type="submit" variant="primary">
                查询
              </Button>
              <Button type="reset" onClick={() => updateQuery(initial)}>
                重置
              </Button>
            </>
          }
        >
          <Field label="客户 / 报关单 / CD / 销售订单" grow>
            <input name="keyword" placeholder="输入关键词" />
          </Field>
          <Field label="资料进度">
            <select name="status" defaultValue="all">
              <option value="all">全部</option>
              <option value="pending_bill">待上传或核对提单</option>
              <option value="pending_contract">待生成或核对合同</option>
              <option value="stale">依据变化待更新</option>
              <option value="complete">资料齐全</option>
            </select>
          </Field>
        </FilterBar>
        <CardContent flush>
          {query.consignee && (
            <Alert tone="info" title={`当前客户范围：${query.consignee}`}>
              <Button size="sm" onClick={() => updateQuery({ ...query, consignee: "", page: 1 })}>
                查看全部客户
              </Button>
            </Alert>
          )}
          {state.kind === "loading" && <Skeleton rows={4} label="正在读取报关资料" />}
          {state.kind === "error" && (
            <ErrorState
              title="报关资料读取失败"
              message={state.message}
              action={<Button onClick={reload}>重试</Button>}
            />
          )}
          {state.kind === "ready" &&
            (state.result.items.length ? (
              <DataTable
                label="直接收汇报关资料"
                columns={columns}
                rows={state.result.items}
                rowKey={(row) => row.declarationNo}
                rowTone={(row) => (row.declarationNo === selected ? "accent" : undefined)}
                minWidth={1100}
              />
            ) : (
              <EmptyState
                title="没有符合条件的直接收汇报关资料"
                description="海关回执关联 NS 报关单且判定为直接收汇后，在这里办理资料。"
              />
            ))}
        </CardContent>
        {state.kind === "ready" && state.result.total > 0 && (
          <CardFooter>
            <Pagination
              label="直接收汇资料分页"
              total={state.result.total}
              unit="票"
              page={state.result.page}
              pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
              pageSize={query.pageSize}
              pageSizes={[20, 50]}
              onPageChange={(page) => updateQuery({ ...query, page })}
              onPageSizeChange={(pageSize) => updateQuery({ ...query, pageSize, page: 1 })}
            />
          </CardFooter>
        )}
      </Card>
      {selected && (
        <section ref={detail} tabIndex={-1} aria-label={`办理资料 ${selected}`}>
          <Card>
            <CardHeader
              title={`办理资料 · ${selected}`}
              description="上传提单并核对字段，确认买卖双方及合同条款后生成销售合同。"
              actions={<Button onClick={() => select("")}>关闭资料</Button>}
            />
            <CardContent>
              <BatchDocuments key={selected} target={selected} onChanged={reload} />
            </CardContent>
          </Card>
        </section>
      )}
      <Alert tone="info" title="资料与收款分别记录">
        办理资料不登记回款、不创建收款批次，也不改变客户总账金额。
      </Alert>
    </div>
  );
}
