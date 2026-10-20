import { writebackTime, type WritebackRequest } from "../types";

/** 发票与本次回写概况；全部字段来自后端预览快照。 */
export function PreviewSummary({ data }: { data: WritebackRequest }) {
  const facts: [string, string, string?][] = [
    ["供应商发票编码", data.invoiceNo, "wb-mono"],
    ["开票日期", data.invoiceDate],
    ["供应商", `${data.vendorName}（${data.vendorRef}）`],
    ["发票价税合计", `${data.invoiceAmount} ${data.currency}`, "wb-mono"],
    ["本次实收合计", `${data.totalAmount} ${data.currency}`, "wb-mono wb-strong"],
    ["写入账套", data.account],
    ["请求编号", data.requestId, "wb-mono"],
    ["预览生成", `${writebackTime(data.createdAt)} · ${data.createdBy}`],
  ];
  return (
    <section className="wb-panel" aria-label="发票信息">
      <dl className="wb-facts">
        {facts.map(([label, value, className]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className={className}>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
