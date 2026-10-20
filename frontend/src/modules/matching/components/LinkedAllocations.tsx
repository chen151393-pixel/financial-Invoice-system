import { Fragment, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { Allocation } from "../types/matching";

const time = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—";

/**
 * 已关联（已通过且依据有效）的分配。删除关联调用后端“取消分配”：
 * 记录保留可追溯，原因必填，收票进度由后端回退；能否删除只看后端 cancel.allowed。
 */
export function LinkedAllocations({
  allocations,
  busy,
  onCancel,
}: {
  allocations: Allocation[];
  busy: boolean;
  onCancel: (id: string, reason: string) => Promise<boolean>;
}) {
  const [target, setTarget] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  if (allocations.length === 0) return <p className="matching-help">暂无已关联的子采购行。</p>;
  return (
    <div
      className="matching-table-wrap"
      role="region"
      aria-label="已关联的子采购行，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
      tabIndex={0}
    >
      <table className="matching-table">
        <thead>
          <tr>
            <th scope="col">子采购单 / 品名</th>
            <th scope="col">来源</th>
            <th scope="col" className="matching-number">
              数量
            </th>
            <th scope="col" className="matching-number">
              含税金额
            </th>
            <th scope="col">审核</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {allocations.map((allocation) => (
            <Fragment key={allocation.id}>
              <tr>
                <td>
                  {allocation.purchase?.orderNo || "—"}
                  <small>
                    {allocation.purchase?.item || "—"} · {allocation.purchase?.unit || "单位缺失"}
                  </small>
                </td>
                <td>
                  <span
                    className="matching-tag"
                    data-source={allocation.tier === "manual" ? "manual" : "system"}
                  >
                    {allocation.tier === "manual" ? "人工关联" : "系统建议"}
                  </span>
                </td>
                <td className="matching-number">{allocation.quantity}</td>
                <td className="matching-number">{allocation.amount}</td>
                <td>
                  {allocation.reviewedBy ?? "—"}
                  <small>{time(allocation.reviewedAt)}</small>
                </td>
                <td>
                  <Button
                    className="matching-danger"
                    disabled={busy || !allocation.cancel.allowed}
                    title={allocation.cancel.allowed ? undefined : allocation.cancel.reason}
                    aria-expanded={target === allocation.id}
                    onClick={() => {
                      setTarget(target === allocation.id ? null : allocation.id);
                      setReason("");
                    }}
                  >
                    删除关联
                  </Button>
                  {!allocation.cancel.allowed && <small>{allocation.cancel.reason}</small>}
                </td>
              </tr>
              {target === allocation.id && (
                <tr>
                  <td colSpan={6} className="matching-confirm">
                    <form
                      className="matching-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void onCancel(allocation.id, reason).then((done) => done && setTarget(null));
                      }}
                    >
                      <strong>删除与 {allocation.purchase?.orderNo || "该子采购行"} 的关联？</strong>
                      <span className="matching-help">
                        删除后 {allocation.quantity} / {allocation.amount}{" "}
                        不再计入收票进度，开票任务进度随之回退；记录保留可追溯。
                      </span>
                      <label>
                        删除原因（必填）
                        <textarea
                          rows={2}
                          maxLength={300}
                          value={reason}
                          disabled={busy}
                          onChange={(event) => setReason(event.target.value)}
                        />
                      </label>
                      <div className="matching-row">
                        <Button
                          type="submit"
                          className="matching-danger matching-danger--solid"
                          disabled={busy}
                        >
                          {busy ? "提交中…" : "确认删除关联"}
                        </Button>
                        <Button disabled={busy} onClick={() => setTarget(null)}>
                          返回
                        </Button>
                      </div>
                    </form>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
