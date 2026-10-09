import { useState } from "react";
import type { View } from "../types";

export function MatchDetail({
  notify,
  back,
  navigate,
}: {
  notify: (message: string) => void;
  back: () => void;
  navigate: (view: View) => void;
}) {
  const orders = [
    {
      id: "81642",
      no: "PO-202608-01426",
      sub: "ZCG-01426-03",
      receipt: "IR-202608-00881 · ID 92811",
      sku: "折叠露营桌 · 320件",
      amount: 78240,
      score: 99,
      reason: "供应商、金额、SKU、入库日期全部一致",
    },
    {
      id: "81657",
      no: "PO-202608-01431",
      sub: "ZCG-01431-01",
      receipt: "IR-202608-00896 · ID 92843",
      sku: "露营收纳箱 · 180件",
      amount: 48310,
      score: 96,
      reason: "供应商、金额、SKU 一致，日期相差 1 天",
    },
    {
      id: "81498",
      no: "PO-202608-01398",
      sub: "ZCG-01398-02",
      receipt: "IR-202608-00837 · ID 92695",
      sku: "户外折叠椅 · 200件",
      amount: 43600,
      score: 72,
      reason: "供应商一致，金额与商品名称近似",
    },
  ];
  const [selected, setSelected] = useState(["81642", "81657"]);
  const [confirmed, setConfirmed] = useState(false);
  const total = orders.filter((o) => selected.includes(o.id)).reduce((sum, o) => sum + o.amount, 0);
  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  return (
    <>
      <button className="back-button" onClick={back}>
        ← 返回进项发票
      </button>
      <div className="match-head-card">
        <div>
          <span className="eyebrow">匹配单 MAT-202608-01876 · Trace TRC-8F21E4</span>
          <h2>发票 24442000000187654321</h2>
          <p>深圳主体 · CNY · 会计期间 2026-08</p>
        </div>
        <div className="score-ring">
          <strong>98</strong>
          <span>匹配置信度</span>
        </div>
        <div className="match-head-stat">
          <span>价税合计</span>
          <strong>¥ 126,550.00</strong>
          <small>未税 ¥111,992.48 · 税额 ¥14,557.52</small>
        </div>
        <span className="relation-hero">一票多单</span>
      </div>
      <div className="match-layout">
        <article className="panel invoice-document">
          <div className="panel-head">
            <div>
              <h2>柠檬云发票信息</h2>
              <p>批次 LY-0825-1028 · 已通过税务查验</p>
            </div>
            <button className="tool-button">查看原票 ↗</button>
          </div>
          <div className="invoice-paper">
            <div className="paper-title">
              <span>电子发票（增值税专用发票）</span>
              <i>已查验</i>
            </div>
            <div className="paper-grid">
              <div>
                <span>购买方</span>
                <strong>深圳市新思跨境电子商务有限公司</strong>
                <small>91440300MA5F******</small>
              </div>
              <div>
                <span>销售方</span>
                <strong>深圳市华盛塑胶制品有限公司</strong>
                <small>Vendor VND-10486 · Internal ID 4821</small>
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>项目名称</th>
                  <th>规格型号</th>
                  <th>数量</th>
                  <th>金额</th>
                  <th>税率</th>
                  <th>税额</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>*塑料制品*折叠露营桌</td>
                  <td>HS-ZD120</td>
                  <td>320</td>
                  <td>¥69,238.94</td>
                  <td>13%</td>
                  <td>¥9,001.06</td>
                </tr>
                <tr>
                  <td>*塑料制品*露营收纳箱</td>
                  <td>HS-SN50</td>
                  <td>180</td>
                  <td>¥42,753.54</td>
                  <td>13%</td>
                  <td>¥5,556.46</td>
                </tr>
              </tbody>
            </table>
            <div className="paper-total">
              <span>价税合计（小写）</span>
              <strong>¥ 126,550.00</strong>
            </div>
          </div>
          <div className="rule-evidence">
            <h3>自动匹配依据</h3>
            <div>
              <span>
                <i>✓</i>Vendor 税号完全一致
              </span>
              <span>
                <i>✓</i>价税合计完全一致
              </span>
              <span>
                <i>✓</i>发票日期在 Item Receipt 后 15 天内
              </span>
              <span>
                <i>✓</i>商品名称与 Item / SKU 映射一致
              </span>
            </div>
          </div>
        </article>
        <article className="panel candidates">
          <div className="panel-head">
            <div>
              <h2>NetSuite 候选业务单据</h2>
              <p>
                已选择 {selected.length} 笔 · 合计 ¥
                {total.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
              </p>
            </div>
            <span className="auto-label">规则自动推荐</span>
          </div>
          <div className="mapping-note">
            “子采购单”映射为 NetSuite 自定义字段 <b>custbody_sub_po_no</b>
          </div>
          <div className="relationship-visual">
            <span>柠檬云发票</span>
            <i>→</i>
            <div>
              <b>Purchase Order / Item Receipt 1</b>
              <b>Purchase Order / Item Receipt 2</b>
            </div>
          </div>
          <div className="candidate-list">
            {orders.map((order) => (
              <button
                className={`candidate-card ${selected.includes(order.id) ? "selected" : ""}`}
                key={order.id}
                onClick={() => toggle(order.id)}
              >
                <i className="candidate-check">{selected.includes(order.id) ? "✓" : ""}</i>
                <div className="candidate-main">
                  <span>
                    子采购单 {order.sub} · PO Internal ID {order.id}
                  </span>
                  <strong>{order.no}</strong>
                  <small>{order.receipt}</small>
                  <small>{order.sku}</small>
                  <em>{order.reason}</em>
                </div>
                <div className="candidate-score">
                  <strong>{order.score}%</strong>
                  <span>¥{order.amount.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span>
                </div>
              </button>
            ))}
          </div>
          <button className="add-order">＋ 手动关联其他 Purchase Order / Expense Report</button>
          <div className="match-balance">
            <div>
              <span>发票金额</span>
              <strong>¥126,550.00</strong>
            </div>
            <div>
              <span>已关联业务金额</span>
              <strong>¥{total.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</strong>
            </div>
            <div className={total === 126550 ? "balanced" : "unbalanced"}>
              <span>匹配差额</span>
              <strong>
                ¥{Math.abs(126550 - total).toLocaleString("zh-CN", { minimumFractionDigits: 2 })}
              </strong>
            </div>
          </div>
          <div className="writeback-preview">
            <span>回写对象</span>
            <strong>Vendor Bill 自定义字段 + 关联明细</strong>
            <small>实际写入仅在审批后执行，失败自动进入回写队列</small>
          </div>
          <div className="sticky-actions three">
            <button className="button secondary" onClick={() => notify("已保存为待确认匹配")}>
              保存待确认
            </button>
            <button
              className="button outline-primary"
              disabled={total !== 126550}
              onClick={() => {
                setConfirmed(true);
                notify("匹配已确认，尚未写入 NetSuite");
              }}
            >
              确认匹配
            </button>
            <button
              className="button primary"
              disabled={total !== 126550}
              onClick={() => {
                setConfirmed(true);
                notify("已提交 NetSuite 回写队列：WB-202608-00482");
                navigate("writeback");
              }}
            >
              {confirmed ? "提交回写 NetSuite" : "确认并回写 NS"}
            </button>
          </div>
        </article>
      </div>
    </>
  );
}
