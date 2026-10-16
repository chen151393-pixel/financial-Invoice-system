import { Button } from "../../../shared/components/Button";
import type { Association, PreviewPage, PreviewRow } from "../types/external-group";
export function GroupImportRows({
  data,
  choices,
  busy,
  editing,
  onEdit,
  onClear,
}: {
  data: PreviewPage;
  choices: Record<number, Association>;
  busy: boolean;
  editing: boolean;
  onEdit: (row: PreviewRow) => void;
  onClear: (rowNo: number) => void;
}) {
  return (
    <div
      className="it-table-wrap sg-table"
      role="region"
      aria-label="外部群导入预览，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表区域需支持键盘横向滚动。
      tabIndex={0}
    >
      <table className="it-table eg-table">
        <thead>
          <tr>
            <th scope="col">Excel 行 / 群名</th>
            <th scope="col">群主 / 外部群 ID</th>
            <th scope="col">匹配预览</th>
            <th scope="col">已选供应商</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((row) => (
            <tr key={row.rowNo}>
              <td>
                <strong>{row.groupName || "群名未填写"}</strong>
                <small>
                  第 {row.rowNo} 行{row.catalogRevision ? " · 更新已导入群" : " · 新群"}
                </small>
              </td>
              <td>
                {row.group ? (
                  <>
                    {row.group.employee}
                    <small>{row.group.userid}</small>
                    <small>{row.group.chatId}</small>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>
                {row.issue ? (
                  <span className="eg-error">错误：{row.issue}</span>
                ) : (
                  <>
                    {row.candidateCount ? `${row.candidateCount} 个候选，需核对` : "未匹配，请手动关联"}
                    {row.candidates.map((c) => (
                      <small key={c.supplierId}>
                        {c.supplierName} · {c.account} · {c.reason}
                      </small>
                    ))}
                  </>
                )}
              </td>
              <td>
                {choices[row.rowNo] ? (
                  <>
                    {choices[row.rowNo].supplier.supplierName}
                    <small>{choices[row.rowNo].supplier.account}</small>
                  </>
                ) : (
                  "暂不关联"
                )}
              </td>
              <td>
                <div className="sg-row">
                  <Button
                    disabled={busy || editing || !!row.issue || !data.confirm.allowed}
                    onClick={() => onEdit(row)}
                  >
                    匹配供应商
                  </Button>
                  {choices[row.rowNo] && (
                    <Button disabled={busy || editing} onClick={() => onClear(row.rowNo)}>
                      清除选择
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
