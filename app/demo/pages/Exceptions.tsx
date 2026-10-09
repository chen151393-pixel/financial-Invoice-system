import { useState } from "react";
import { exceptionRows } from "../fixtures";

export function Exceptions({ notify }: { notify: (message: string) => void }) {
  const [category, setCategory] = useState("全部异常");
  const [selected, setSelected] = useState(0);
  const current = exceptionRows[selected];
  return (
    <div className="exception-layout">
      <aside className="exception-nav panel">
        <div className="panel-head">
          <div>
            <h2>异常池</h2>
            <p>共 47 项待处理</p>
          </div>
        </div>
        {[
          { name: "全部异常", count: 47 },
          { name: "金额不一致", count: 16 },
          { name: "找不到业务单", count: 12 },
          { name: "部分开票", count: 8 },
          { name: "重复发票", count: 3 },
          { name: "回写失败", count: 3 },
        ].map((item) => (
          <button
            className={category === item.name ? "active" : ""}
            key={item.name}
            onClick={() => setCategory(item.name)}
          >
            <span>{item.name}</span>
            <b>{item.count}</b>
          </button>
        ))}
        <div className="exception-tip">
          <strong>关账提示</strong>
          <p>9 项影响 2026-08 会计期间，请优先处理高风险异常。</p>
        </div>
      </aside>
      <article className="panel exception-list-panel">
        <div className="exception-toolbar">
          <label className="search-box">
            <span>⌕</span>
            <input placeholder="搜索异常单 / 供应商" />
          </label>
          <button className="tool-button">责任人⌄</button>
        </div>
        <div className="exception-list">
          {exceptionRows.map((row, index) => (
            <button
              className={selected === index ? "selected" : ""}
              key={row.id}
              onClick={() => setSelected(index)}
            >
              <div className={`risk-flag ${row.level === "高" ? "high" : "mid"}`}>{row.level}</div>
              <div className="exception-item-main">
                <span>
                  {row.type}
                  <small>{row.id}</small>
                </span>
                <strong>{row.supplier}</strong>
                <p>
                  责任人 {row.owner} · {row.date}
                </p>
              </div>
              <b className="exception-diff">{row.diff}</b>
            </button>
          ))}
        </div>
      </article>
      <article className="panel exception-detail">
        <div className="detail-banner">
          <div>
            <span>当前异常</span>
            <h2>{current.type}</h2>
            <p>
              {current.id} · Trace ID {current.trace}
            </p>
          </div>
          <span className="risk-pill">{current.level}风险</span>
        </div>
        <div className="audit-strip">
          <span>责任人：{current.owner}</span>
          <span>SLA：今日 18:00</span>
          <span>期间：2026-08</span>
        </div>
        <div className="detail-section">
          <h3>三方差异核对</h3>
          <div className="compare-grid three">
            <div>
              <span>柠檬云发票</span>
              <strong>¥32,680.00</strong>
              <small>批次 LY-0825-0940</small>
            </div>
            <div>
              <span>NS 业务应付</span>
              <strong>¥31,400.00</strong>
              <small>Expense Report ID 77421</small>
            </div>
            <div>
              <span>NS Vendor Bill</span>
              <strong>¥31,400.00</strong>
              <small>VB ID 99831</small>
            </div>
          </div>
          <div className="difference-line">
            <span>金额差异</span>
            <strong>+ ¥1,280.00</strong>
          </div>
        </div>
        <div className="detail-section">
          <h3>系统判断</h3>
          <div className="system-reason">
            <i>!</i>
            <p>
              发票金额比 NetSuite 业务单高 4.08%，超过允许差异阈值
              0.5%。可能存在未录入服务费或关联单据不完整。
            </p>
          </div>
        </div>
        <div className="detail-section">
          <h3>建议处理方式</h3>
          <label className="radio-option selected">
            <input type="radio" defaultChecked aria-label="拆分发票金额" name="resolution" />
            <span>
              <strong>拆分发票金额</strong>
              <small>¥31,400.00 关联当前费用单，差额进入待匹配池</small>
            </span>
          </label>
          <label className="radio-option">
            <input type="radio" aria-label="补充关联业务单" name="resolution" />
            <span>
              <strong>补充关联业务单</strong>
              <small>搜索 Purchase Order、Expense Report 或自定义子采购单</small>
            </span>
          </label>
          <label className="radio-option">
            <input type="radio" aria-label="退回供应商重开" name="resolution" />
            <span>
              <strong>退回供应商重开</strong>
              <small>标记开票错误并保留完整审计轨迹</small>
            </span>
          </label>
        </div>
        <label className="note-field">
          <span>处理备注</span>
          <textarea placeholder="请输入处理说明（选填）" />
        </label>
        <div className="detail-actions">
          <button className="button secondary" onClick={() => notify(`异常已转交 ${current.owner}`)}>
            转交处理
          </button>
          <button
            className="button primary"
            onClick={() => notify("异常已处理，操作日志 ALOG-008721 已生成")}
          >
            确认并完成
          </button>
        </div>
      </article>
    </div>
  );
}
