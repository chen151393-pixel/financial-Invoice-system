import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { money } from "../../../shared/format/money";
import type { TodoKind, Workbench } from "../types/workbench";

export function WorkbenchAttention({
  data,
  onSelect,
}: {
  data: Workbench;
  onSelect: (kind: TodoKind) => void;
}) {
  return (
    <aside className="wb-aside">
      <section className="wb-panel">
        <div className="wb-panel__head">
          <h2>需要关注</h2>
          <span className="wb-count">优先处理</span>
        </div>
        <div className="wb-attention">
          <span className="wb-attention__icon" aria-hidden="true">
            !
          </span>
          <div>
            <h3>已确认分配待复核</h3>
            <p>{data.counts.reverify} 项发票待办需核实当前依据，复核通过后才计入有效收票。</p>
            <Button onClick={() => onSelect("matching")}>查看比对待办 →</Button>
          </div>
        </div>
        <div className="wb-attention">
          <span className="wb-attention__icon" aria-hidden="true">
            ↗
          </span>
          <div>
            <h3>关联资料与开票准备</h3>
            <p>
              {data.counts.blocked} 张报关单缺少子采购关联；{data.counts.preparation} 项任务待备合同或通知。
            </p>
            <Button onClick={() => onSelect("review")}>查看核对待办 →</Button>
            <Button onClick={() => onSelect("task")}>查看开票待办 →</Button>
          </div>
        </div>
      </section>
      <section className="wb-panel">
        <div className="wb-panel__head">
          <h2>本月任务完成进度</h2>
          <small>{data.month.month}</small>
        </div>
        <div className="wb-progress">
          <p className="wb-progress__value">
            <strong>{data.month.percent ?? "—"}</strong>
            {data.month.percent !== null && "%"}
            <span>
              已完成 {data.month.completed} / {data.month.total} 项
            </span>
          </p>
          {data.month.percent !== null ? (
            <div className="wb-track" role="img" aria-label={`本月新建任务完成 ${data.month.percent}%`}>
              <span style={{ width: `${data.month.percent}%` }} />
            </div>
          ) : (
            <p>本月暂无新建任务</p>
          )}
          <p className="wb-caption">本月新建且未被替代的任务；完成含按差异结束。</p>
          {data.month.received.map((item) => (
            <p className="wb-amount-line" key={item.currency}>
              <span>有效已收票金额</span>
              <strong>
                {item.currency || "币种待核实"} {money(item.amount)}
              </strong>
            </p>
          ))}
        </div>
        <div className="wb-panel__foot">
          <Link to={paths.sync}>数据同步 →</Link>
          <Link to={paths.tasks}>开票跟进 →</Link>
        </div>
      </section>
    </aside>
  );
}
