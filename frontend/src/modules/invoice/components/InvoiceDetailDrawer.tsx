import { useEffect, useRef } from "react";
import { Button } from "../../../shared/components/Button";
import type { MatchingSummary } from "../../matching/api";
import type { InvoiceDetail } from "../types/invoice";
import { money, shown } from "./format";
import "./invoice-detail.css";

const LINE_HEADERS = [
  "行号",
  "商品名称",
  "规格型号",
  "数量",
  "单位",
  "单价",
  "金额",
  "税率",
  "税额",
  "价税合计",
];

export function InvoiceDetailDrawer({
  detail,
  error,
  summary,
  onClose,
  onMatch,
}: {
  detail: InvoiceDetail | null;
  error: string;
  summary?: MatchingSummary;
  onClose: () => void;
  onMatch: (id: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    element?.showModal();
    heading.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="invoice-list__detail"
      aria-labelledby="invoice-detail-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="invoice-list__detail-header">
        <h2 id="invoice-detail-title" ref={heading} tabIndex={-1}>
          发票详情
        </h2>
        <Button className="invoice-list__close" aria-label="关闭票面详情" onClick={onClose}>
          ×
        </Button>
      </div>
      <div className="invoice-list__detail-body">
        {!detail && !error && <p role="status">正在读取发票及商品明细…</p>}
        {error && (
          <p role="alert" className="invoice-list__error">
            {error}，请关闭后重新查看。
          </p>
        )}
        {detail && (
          <>
            <dl className="invoice-list__metadata">
              {[
                ["发票号码", detail.number],
                ["发票类型", detail.type],
                ["供应商", detail.seller],
                ["供应商税号", detail.sellerTaxNo],
                ["开票日期", detail.date],
                ["价税合计", money(detail.gross)],
                ["不含税金额", money(detail.net)],
                ["税额", money(detail.tax)],
                ["币种", detail.currency],
                ["发票代码", detail.invoiceCode],
                ["票面状态", detail.status],
                ["购买方", detail.buyer ?? "来源未提供"],
                ["购买方税号", detail.buyerTaxNo],
                ["备注", detail.remark],
                ["来源", detail.source],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{shown(value)}</dd>
                </div>
              ))}
            </dl>
            <h3 className="invoice-list__section-title">商品明细</h3>
            <p role="status">{detail.detailStatusLabel}</p>
            <div className="invoice-list__table" role="region" aria-label="发票商品明细，可横向滚动">
              <table>
                <caption>票面商品明细 · {detail.lineCount} 行</caption>
                <thead>
                  <tr>
                    {LINE_HEADERS.map((text) => (
                      <th key={text} scope="col">
                        {text}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.lines.map((line) => (
                    <tr key={line.id}>
                      {[
                        line.number,
                        line.item,
                        line.specification,
                        line.quantity,
                        line.unit,
                        line.unitPrice,
                        line.net,
                        line.taxRate,
                        line.tax,
                        line.gross,
                      ].map((value, index) => (
                        <td key={index}>{shown(value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className="invoice-list__section-title">子采购比对</h3>
            <p className="invoice-list__detail-empty">
              {summary ? `${summary.label} · 已通过 ${summary.confirmed} 行` : "比对状态读取中…"}
              <Button className="invoice-list__view" onClick={() => onMatch(detail.id)}>
                查看比对
              </Button>
            </p>
          </>
        )}
      </div>
    </dialog>
  );
}
