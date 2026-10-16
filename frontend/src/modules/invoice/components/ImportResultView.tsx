import { useRef } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import type { ImportResult } from "../types/invoice";

const ACTIONS = {
  updated: ["追加新版本", "新版本已保存"],
  new: ["新增 · 待比对", "已入库 · 已生成比对建议"],
  unchanged: ["重复 · 跳过", "重复 · 跳过"],
  conflict: ["冲突 · 需核实", "冲突 · 需核实"],
} as const;

export function ImportResultView({
  result,
  busy,
  onConfirm,
}: {
  result: ImportResult;
  busy: boolean;
  onConfirm: () => void;
}) {
  const table = useRef<HTMLDivElement>(null);
  return (
    <>
      <div className="invoice-import__summary" role="status">
        <strong>{result.message}</strong>
        <p>{result.filename}</p>
        <p>
          文件共 {result.sourceInvoiceCount} 张 · 导入类型：{result.businessType} · 其他类型已跳过{" "}
          {result.excludedCount} 张
        </p>
        <p>
          本次范围 {result.invoiceCount} 张发票 / {result.lineCount} 行明细 ·{" "}
          {result.saved ? "已新增" : "待新增"} {result.created} 张 · 新版本 {result.updated} 张 · 重复{" "}
          {result.unchanged} 张 · 冲突 {result.conflicts} 张
        </p>
        <p>本次范围价税合计：{result.amount}（人民币）</p>
      </div>
      <ul className="invoice-import__warnings">
        {result.warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
      {!result.saved && (
        <div className="invoice-import__actions">
          <Button variant="primary" disabled={busy || !result.allowed} onClick={() => onConfirm()}>
            确认导入数据库
          </Button>
          <span>{result.reason}；重复记录跳过，冲突时整批不写入。</span>
        </div>
      )}
      <div className="invoice-import__actions" aria-label="表格滚动">
        <Button onClick={() => table.current?.scrollBy({ left: -320 })}>向左查看列</Button>
        <Button onClick={() => table.current?.scrollBy({ left: 320 })}>向右查看列</Button>
      </div>
      <div
        className="sync-page__table invoice-import__table"
        ref={table}
        role="region"
        aria-label="发票导入核对表，可横向滚动"
      >
        <table>
          <caption>{result.saved ? "本次导入结果" : "导入前核对"}</caption>
          <thead>
            <tr>
              <th scope="col">发票号码</th>
              <th scope="col">开票日期</th>
              <th scope="col">供应商</th>
              <th scope="col">业务类型</th>
              <th scope="col">来源状态</th>
              <th scope="col">明细行数</th>
              <th scope="col">价税合计</th>
              <th scope="col">{result.saved ? "处理结果" : "预计处理"}</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => (
              <tr key={row.number}>
                <td>{row.number}</td>
                <td>{row.date}</td>
                <td>{row.seller}</td>
                <td>{row.businessType}</td>
                <td>{row.status}</td>
                <td>{row.lineCount}</td>
                <td className="invoice-import__amount">{row.amount}</td>
                <td>{ACTIONS[row.action][result.saved ? 1 : 0]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.saved && (
        <p>
          发票已保存在数据库。<Link to={paths.invoices}>查看已入库发票</Link>
          ；重新选择同一文件预览，可以核实重复记录。
        </p>
      )}
    </>
  );
}
