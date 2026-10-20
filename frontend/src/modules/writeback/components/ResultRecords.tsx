import type { WritebackRequest } from "../types";

/** 执行结果的 NS 记录与账单回读核实；“写入后已收”缺失表示尚未回读，不显示为 0。 */
export function ResultRecords({ data }: { data: WritebackRequest }) {
  return (
    <>
      {data.records.length > 0 && (
        <section className="wb-panel" aria-labelledby="wb-records-title">
          <h2 id="wb-records-title" className="wb-section-title">
            NS 记录
          </h2>
          <ul className="wb-records">
            {data.records.map((record) =>
              record.url ? (
                <li key={record.label}>
                  <a href={record.url} target="_blank" rel="noreferrer">
                    {record.label}（在 NS 中打开）
                  </a>
                </li>
              ) : (
                <li key={record.label}>{record.label}</li>
              ),
            )}
          </ul>
        </section>
      )}
      {data.bills.length > 0 && (
        <section className="wb-panel wb-panel--flush" aria-labelledby="wb-bills-title">
          <h2 id="wb-bills-title" className="wb-section-title wb-section-head">
            账单累计已收核实
          </h2>
          <div className="wb-table-scroll">
            <table className="wb-table">
              <thead>
                <tr>
                  <th scope="col">账单编号</th>
                  <th scope="col">子采购订单</th>
                  <th scope="col" className="wb-num">
                    写入前已收
                  </th>
                  <th scope="col" className="wb-num">
                    本次实收
                  </th>
                  <th scope="col" className="wb-num">
                    写入后已收（NS 回读）
                  </th>
                  <th scope="col">核实</th>
                </tr>
              </thead>
              <tbody>
                {data.bills.map((bill) => (
                  <tr key={`${bill.billNo}:${bill.subPoNo}`}>
                    <td className="wb-nowrap">{bill.billNo}</td>
                    <td className="wb-nowrap">{bill.subPoNo}</td>
                    <td className="wb-num">{bill.before}</td>
                    <td className="wb-num">{bill.amount}</td>
                    <td className="wb-num wb-strong">{bill.after ?? "未回读"}</td>
                    <td>
                      <span className={bill.passed ? "wb-note--succeeded" : "wb-note--failed"}>
                        {bill.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
