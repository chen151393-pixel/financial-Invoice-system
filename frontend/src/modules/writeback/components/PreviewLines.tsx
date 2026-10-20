import { writebackTime, type WritebackRequest } from "../types";

/** 列顺序与 NS“供应商发票勾选平台”一致；应收、已收、未收为预览时 NS 实时读取的后端文本。 */
export function PreviewLines({ data }: { data: WritebackRequest }) {
  return (
    <section className="wb-panel wb-panel--flush" aria-labelledby="wb-lines-title">
      <div className="wb-section-head">
        <h2 id="wb-lines-title" className="wb-section-title">
          将写入 NS 的明细 <span className="wb-muted">· {data.lines.length} 张账单</span>
        </h2>
        <span className="wb-muted">NS 数据读取于 {writebackTime(data.readAt)}</span>
      </div>
      <div className="wb-table-scroll">
        <table className="wb-table">
          <thead>
            <tr>
              <th scope="col">账单编号</th>
              <th scope="col">母采购订单</th>
              <th scope="col">子采购订单</th>
              <th scope="col" className="wb-num">
                应收金额
              </th>
              <th scope="col" className="wb-num">
                已收金额
              </th>
              <th scope="col" className="wb-num">
                未收金额
              </th>
              <th scope="col" className="wb-num wb-highlight">
                本次实收
              </th>
              <th scope="col" className="wb-num">
                写入后已收
              </th>
              <th scope="col">校验</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((line) => (
              <tr key={`${line.billNo}:${line.subPoNo}`}>
                <td className="wb-nowrap">{line.billNo}</td>
                <td className="wb-nowrap">{line.poNo}</td>
                <td className="wb-nowrap">{line.subPoNo}</td>
                <td className="wb-num">{line.due}</td>
                <td className="wb-num">{line.received}</td>
                <td className="wb-num">{line.remaining}</td>
                <td className="wb-num wb-highlight wb-strong">{line.amount}</td>
                <td className="wb-num">{line.receivedAfter}</td>
                <td>
                  <span className={line.check.passed ? "wb-note--succeeded" : "wb-note--failed"}>
                    {line.check.label}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={6}>
                {data.totalLabel}
              </th>
              <td className="wb-num wb-highlight wb-strong">{data.totalAmount}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
      {data.operations.length > 0 && (
        <details className="wb-operations">
          <summary>将创建和更新的 NS 记录</summary>
          <ul>
            {data.operations.map((operation) => (
              <li key={operation}>{operation}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
