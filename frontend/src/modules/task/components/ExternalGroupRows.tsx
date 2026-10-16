import { Button } from "../../../shared/components/Button";
import type { CatalogPage, CatalogItem } from "../types/external-group";
import { formatTime } from "./format";
export function ExternalGroupRows({
  data,
  disabled,
  onEdit,
}: {
  data: CatalogPage;
  disabled: boolean;
  onEdit: (group: CatalogItem) => void;
}) {
  return (
    <div
      className="it-table-wrap sg-table"
      role="region"
      aria-label="外部群目录，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表区域需支持键盘横向滚动。
      tabIndex={0}
    >
      <table className="it-table eg-table">
        <thead>
          <tr>
            <th scope="col">外部群</th>
            <th scope="col">群主</th>
            <th scope="col">人数 / 创建时间</th>
            <th scope="col">关联供应商</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((group) => (
            <tr key={group.chatId}>
              <td>
                <strong>{group.groupName}</strong>
                <small>{group.chatId}</small>
                <small>Excel：{group.filename}</small>
              </td>
              <td>
                {group.employee}
                <small>{group.userid}</small>
                <small>{group.department}</small>
              </td>
              <td>
                {group.memberCount === null ? "人数未提供" : `${group.memberCount} 人`}
                <small>{group.createdAt ? formatTime(group.createdAt) : "未提供"}</small>
              </td>
              <td>
                {group.suppliers.length
                  ? group.suppliers.map((s) => (
                      <p key={s.supplierId}>
                        {s.supplierName}
                        <small>
                          {s.account} · {s.binding?.enabled ? "启用" : "停用"}
                        </small>
                      </p>
                    ))
                  : "未关联，可手动维护"}
              </td>
              <td>
                <Button disabled={disabled} onClick={() => onEdit(group)}>
                  关联供应商
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
