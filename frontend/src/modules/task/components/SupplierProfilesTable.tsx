import { Button } from "../../../shared/components/Button";
import type { SupplierProfile } from "../types/supplier-group";
import { formatTime } from "./format";

export function SupplierProfilesTable({
  items,
  disabled,
  onEdit,
}: {
  items: SupplierProfile[];
  disabled: boolean;
  onEdit: (item: SupplierProfile) => void;
}) {
  return (
    <div
      className="it-table-wrap sg-table"
      role="region"
      aria-label="供应商档案，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表支持键盘聚焦滚动。
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th scope="col">供应商 / NS 环境</th>
            <th scope="col">供应商外部群</th>
            <th scope="col">群主</th>
            <th scope="col">绑定状态 / 更新时间</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.supplierId}>
              <td>
                <strong>{item.supplierName}</strong>
                <span className="it-secondary">
                  {item.account} · NS 供应商 ID：{item.nsInternalId}
                </span>
              </td>
              <td>
                {item.binding?.groupName || "尚未绑定外部群"}
                <span className="it-secondary">{item.binding?.chatId}</span>
              </td>
              <td>
                {item.binding?.employee || "—"}
                <span className="it-secondary">{item.binding?.userid}</span>
              </td>
              <td>
                {item.binding ? (item.binding.enabled ? "已绑定 · 启用" : "已绑定 · 停用") : "未绑定"}
                {item.binding && <span className="it-secondary">{formatTime(item.binding.updatedAt)}</span>}
              </td>
              <td>
                <Button disabled={disabled} onClick={() => onEdit(item)}>
                  维护档案
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
