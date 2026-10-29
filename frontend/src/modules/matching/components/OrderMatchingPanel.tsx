import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { findOrderCandidates } from "../api";
import type { InvoiceMatching } from "../types/matching";
import type { OrderCandidate, OrderCandidates, OrderConfirmBody } from "../types/order-matching";
import { ConversionFields, defaultConversion } from "./ConversionFields";

type Remote =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: OrderCandidates };

export function OrderMatchingPanel({
  invoiceId,
  value,
  busy,
  onConfirm,
}: {
  invoiceId: string;
  value: InvoiceMatching;
  busy: boolean;
  onConfirm: (body: OrderConfirmBody) => Promise<boolean>;
}) {
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [keyword, setKeyword] = useState("");
  const [conversion, setConversion] = useState(defaultConversion);
  const [query, setQuery] = useState({
    keyword: "",
    page: 1,
    conversionNumerator: "1",
    conversionDenominator: "1",
    refresh: 0,
  });
  const [selected, setSelected] = useState<OrderCandidate | null>(null);
  const [note, setNote] = useState("");
  const request = useRef({ key: "", id: "" });

  useEffect(() => {
    let active = true;
    void findOrderCandidates({
      invoiceId,
      keyword: query.keyword,
      page: query.page,
      conversionNumerator: query.conversionNumerator,
      conversionDenominator: query.conversionDenominator,
    })
      .then((data) => {
        if (active) setState({ kind: "ready", data });
      })
      .catch((error: unknown) => {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "整单候选读取失败" });
      });
    return () => {
      active = false;
    };
  }, [invoiceId, value, query]);

  function search(page = 1) {
    setSelected(null);
    setState({ kind: "loading" });
    setQuery({
      keyword,
      page,
      conversionNumerator: conversion.conversionNumerator,
      conversionDenominator: conversion.conversionDenominator,
      refresh: query.refresh + 1,
    });
  }

  async function submit() {
    if (!selected || busy) return;
    const body = {
      ...conversion,
      invoiceId,
      invoiceVersionId: value.invoice.versionId,
      purchaseOrderId: selected.purchaseOrderId,
      fingerprint: selected.fingerprint,
      note,
    };
    const key = JSON.stringify(body);
    if (request.current.key !== key) request.current = { key, id: crypto.randomUUID() };
    if (await onConfirm({ ...body, requestId: request.current.id })) {
      setSelected(null);
      setNote("");
    }
  }

  return (
    <Card aria-label="整张子采购单匹配">
      <CardHeader
        title="整张子采购单匹配"
        description="先选择整单，再核对分配预览。确认会一次保存全部明细，发票票面原始明细保持不变。"
      />
      <div className="matching-body">
        <form
          className="matching-form"
          onSubmit={(event) => {
            event.preventDefault();
            search();
          }}
        >
          <label>
            子采购单／母采购单／供应商
            <input value={keyword} disabled={busy} onChange={(event) => setKeyword(event.target.value)} />
          </label>
          <ConversionFields
            value={conversion}
            busy={busy}
            onChange={(next) => {
              if (
                next.conversionNumerator !== conversion.conversionNumerator ||
                next.conversionDenominator !== conversion.conversionDenominator
              )
                setSelected(null);
              setConversion(next);
            }}
          />
          <Button type="submit" disabled={busy || state.kind === "loading"}>
            查询并更新整单预览
          </Button>
        </form>
        {state.kind === "loading" && <Skeleton label="正在读取整单候选" rows={3} />}
        {state.kind === "error" && (
          <ErrorState
            title="整单候选暂时无法加载"
            message={state.message}
            action={<Button onClick={() => search()}>重新加载</Button>}
          />
        )}
        {state.kind === "ready" &&
          (state.data.rows.length === 0 ? (
            <EmptyState
              title="没有符合条件的整单候选"
              description="请检查单号、供应商和财务审核状态，只有存在有效开票任务的子采购单会进入候选。"
            />
          ) : (
            <>
              <DataTable
                label="整张子采购单候选"
                rows={state.data.rows}
                rowKey={(row) => row.purchaseOrderId}
                columns={[
                  {
                    key: "order",
                    header: "子采购单",
                    render: (row) => (
                      <>
                        {row.orderNo}
                        <p className="matching-help">{row.parentOrderNo}</p>
                        {row.orderMatched && <Badge tone="info">备注命中</Badge>}
                      </>
                    ),
                  },
                  {
                    key: "supplier",
                    header: "供应商／采购公司",
                    render: (row) => (
                      <>
                        {row.supplier}
                        <p className="matching-help">
                          {row.company} · {row.account}
                        </p>
                      </>
                    ),
                  },
                  { key: "lines", header: "整单明细", render: (row) => `${row.lineCount} 行` },
                  {
                    key: "quantity",
                    header: "剩余应开数量",
                    render: (row) => `${row.remainingQuantity ?? "待核实"} ${row.unit}`,
                  },
                  {
                    key: "amount",
                    header: "剩余应开金额",
                    align: "right",
                    render: (row) => `${row.remainingAmount ?? "待核实"} ${row.currency}`,
                  },
                  {
                    key: "action",
                    header: "操作",
                    render: (row) => (
                      <Button
                        disabled={
                          busy ||
                          conversion.conversionNumerator !== query.conversionNumerator ||
                          conversion.conversionDenominator !== query.conversionDenominator
                        }
                        onClick={() => setSelected(row)}
                      >
                        查看整单
                      </Button>
                    ),
                  },
                ]}
              />
              <div className="matching-row">
                <span>
                  共 {state.data.total} 张 · 第 {state.data.page} / {state.data.pages} 页
                </span>
                <Button disabled={busy || state.data.page <= 1} onClick={() => search(state.data.page - 1)}>
                  上一页
                </Button>
                <Button
                  disabled={busy || state.data.page >= state.data.pages}
                  onClick={() => search(state.data.page + 1)}
                >
                  下一页
                </Button>
              </div>
            </>
          ))}
        {selected && (
          <section aria-label="整单分配预览" className="matching-form">
            <h3>{selected.orderNo} · 整单分配预览</h3>
            {selected.warnings.map((warning) => (
              <Alert tone="info" key={warning}>
                {warning}
              </Alert>
            ))}
            {!selected.confirm.allowed && <Alert tone="warning">{selected.confirm.reason}</Alert>}
            {selected.allocations.length > 0 && (
              <DataTable
                label="整单分配明细"
                rows={selected.allocations}
                rowKey={(row) => row.purchaseLineId}
                maxHeight={420}
                columns={[
                  { key: "item", header: "采购品名", render: (row) => row.item },
                  {
                    key: "invoice",
                    header: "分配发票数量",
                    render: (row) => `${row.invoiceQuantity} ${row.invoiceUnit}`,
                  },
                  {
                    key: "purchase",
                    header: "采购数量",
                    render: (row) => `${row.purchaseQuantity} ${row.purchaseUnit}`,
                  },
                  { key: "amount", header: "含税金额", align: "right", render: (row) => row.amount },
                ]}
              />
            )}
            <label>
              整单审核说明
              <textarea
                value={note}
                maxLength={300}
                disabled={busy}
                onChange={(event) => setNote(event.target.value)}
                placeholder="说明票面汇总与采购明细的对应依据；单位不同时请同时填写上方换算证据。"
              />
            </label>
            <Button
              disabled={busy || !selected.confirm.allowed}
              title={selected.confirm.reason}
              onClick={() => void submit()}
            >
              确认整单并分配到 {selected.allocations.length} 行
            </Button>
          </section>
        )}
      </div>
    </Card>
  );
}
