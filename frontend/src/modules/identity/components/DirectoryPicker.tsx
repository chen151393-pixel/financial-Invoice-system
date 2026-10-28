import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import type { useDirectorySelection } from "../hooks/useDirectorySelection";
import { DepartmentTree } from "./DepartmentTree";

type PickerState = ReturnType<typeof useDirectorySelection>;

export function DirectoryPicker({ flow }: { flow: PickerState }) {
  const { preview, members, selection, department, reading, busy } = flow;
  if (!preview) return null;
  const selected = preview.departments.find((d) => d.id === department);
  const whole = selection.departmentIds.includes(department);
  const inherited = !whole && !!members?.coveredDepartmentIds.includes(department);
  const disabled = reading || busy;
  function toggleWhole(checked: boolean) {
    flow.changeSelection({
      ...selection,
      departmentIds: checked
        ? [...selection.departmentIds, department]
        : selection.departmentIds.filter((id) => id !== department),
    });
  }
  return (
    <Card>
      {!preview.departments.length ? (
        <EmptyState
          title="应用可见范围内没有部门"
          description="请检查飞书应用通讯录的授权范围，再重新读取。"
        />
      ) : (
        <div className="identity-directory-layout">
          <DepartmentTree
            items={preview.departments}
            selected={department}
            disabled={busy}
            description={`${preview.departments.length} 个飞书可见部门`}
            onSelect={flow.chooseDepartment}
          />
          <section className="identity-directory-members" aria-label="部门成员选择">
            <CardHeader title={selected?.name ?? "选择部门"} description={selected?.path} />
            <CardContent>
              <div className="identity-directory-modes">
                <label>
                  <input
                    type="radio"
                    name="directory-mode"
                    checked={!whole && !inherited}
                    disabled={disabled || inherited}
                    onChange={() => toggleWhole(false)}
                  />
                  指定成员
                </label>
                <label>
                  <input
                    type="radio"
                    name="directory-mode"
                    checked={whole || inherited}
                    disabled={disabled || inherited}
                    onChange={() => toggleWhole(true)}
                  />
                  整个部门（含下级）
                </label>
              </div>
              <p className="identity-access-muted">
                {inherited
                  ? "已包含在上级部门范围内，请先取消上级部门的整部门选择，才能单独选人。"
                  : whole
                    ? "持续同步本部门及下级部门，后续新增人员也会纳入；新人员仍需授权启用。"
                    : "只同步勾选的成员，可跨部门选择；后续新增人员不会自动纳入。"}
              </p>
            </CardContent>
            <FilterBar
              embedded
              onSubmit={(form) => flow.search(String(new FormData(form).get("query") ?? ""))}
              actions={
                <Button type="submit" disabled={disabled}>
                  查询
                </Button>
              }
            >
              <Field label="成员姓名" grow>
                <input
                  name="query"
                  key={`${department}-${flow.query}`}
                  defaultValue={flow.query}
                  placeholder="搜索当前部门成员"
                />
              </Field>
            </FilterBar>
            {reading ? (
              <Skeleton rows={4} label="正在读取部门成员" />
            ) : flow.memberError ? (
              <ErrorState
                title="成员读取失败"
                message={flow.memberError}
                action={<Button onClick={flow.retryMembers}>重新读取</Button>}
              />
            ) : members && !members.items.length ? (
              <EmptyState title="当前条件下没有成员" description="可更换部门或清空搜索条件。" />
            ) : (
              members && (
                <DataTable
                  label="飞书部门成员"
                  rowKey={(row) => row.id}
                  rows={members.items}
                  minWidth={500}
                  columns={[
                    {
                      key: "select",
                      header: "选择",
                      width: "64px",
                      render: (row) => (
                        <input
                          aria-label={`选择${row.name}`}
                          type="checkbox"
                          checked={row.selected}
                          title={row.coveredByDepartment ? "已包含在整部门范围内" : (row.reason ?? undefined)}
                          disabled={disabled || row.coveredByDepartment || (!row.selectable && !row.selected)}
                          onChange={(e) =>
                            flow.changeSelection({
                              ...selection,
                              userIds: e.target.checked
                                ? [...selection.userIds, row.id]
                                : selection.userIds.filter((id) => id !== row.id),
                            })
                          }
                        />
                      ),
                    },
                    {
                      key: "name",
                      header: "成员",
                      render: (row) => (
                        <div className="identity-member-name">
                          <span className="identity-member-avatar" aria-hidden="true">
                            {row.name.slice(0, 1)}
                          </span>
                          <strong>{row.name}</strong>
                        </div>
                      ),
                    },
                    {
                      key: "department",
                      header: "所属部门",
                      render: (row) =>
                        row.departments.length > 1 ? (
                          <details className="identity-member-departments">
                            <summary>
                              {row.departments[0]} 等 {row.departments.length} 个部门
                            </summary>
                            <span>{row.departments.join("、")}</span>
                          </details>
                        ) : (
                          row.departments[0]
                        ),
                    },
                    {
                      key: "status",
                      header: "平台状态",
                      render: (row) => (
                        <Badge tone={row.selectable ? "neutral" : "warning"}>
                          {row.reason ?? (row.imported ? "已导入" : "未同步")}
                        </Badge>
                      ),
                    },
                  ]}
                />
              )
            )}
            {members && members.total > 50 && (
              <Pagination
                label="部门成员分页"
                total={members.total}
                page={members.page}
                pageCount={Math.ceil(members.total / members.pageSize)}
                pageSize={50}
                pageSizes={[50]}
                disabled={disabled}
                onPageChange={flow.changePage}
                onPageSizeChange={() => {}}
              />
            )}
          </section>
        </div>
      )}
      <CardFooter className="identity-directory-footer">
        <div aria-live="polite">
          {members ? (
            <>
              已选 <strong>{members.selectedCount}</strong> 人
            </>
          ) : (
            "选择范围后确认同步"
          )}
          <p className="identity-access-muted">
            整部门 {selection.departmentIds.length} 个 · 单独选择 {selection.userIds.length} 人（按人员去重）
          </p>
        </div>
        <div className="identity-directory-actions">
          <Button disabled={busy} onClick={flow.closePreview}>
            返回已导入员工
          </Button>
          <Button disabled={disabled} onClick={flow.cancel}>
            撤销选择更改
          </Button>
          <Button
            variant="primary"
            disabled={disabled || !!flow.memberError}
            onClick={() => void flow.review()}
          >
            确认同步范围
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}
