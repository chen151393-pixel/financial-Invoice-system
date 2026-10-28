import { Alert, Button, Card, CardContent, CardFooter, CardHeader } from "../../../shared/components/ui";
import type { DirectoryPlan } from "../types";

export function DirectoryConfirmation({
  plan,
  busy,
  onBack,
  onConfirm,
}: {
  plan: DirectoryPlan;
  busy: boolean;
  onBack: () => void;
  onConfirm: () => void;
}) {
  return (
    <Card>
      <CardHeader
        title="确认本次同步"
        description="本次选择将替换当前同步范围。请核对范围和移出人员后再确认。"
      />
      <CardContent>
        <dl className="identity-directory-summary">
          <div>
            <dt>整部门持续同步</dt>
            <dd>{plan.departmentNames.join("、") || "未选择"}</dd>
          </div>
          <div>
            <dt>单独选择人员</dt>
            <dd>{plan.userNames.join("、") || "未选择"}</dd>
          </div>
          <div>
            <dt>去重后人数</dt>
            <dd>
              {plan.selectedCount} 人（新增 {plan.addedCount} 人，更新已有 {plan.retainedCount} 人）
            </dd>
          </div>
        </dl>
        {plan.removedNames.length > 0 && (
          <Alert tone="warning" title={`将移出同步范围：${plan.removedNames.length} 人`}>
            {plan.removedNames.join("、")}。确认后这些人员无法登录，现有会话在下一次请求失效。
          </Alert>
        )}
        {plan.unavailableCount > 0 && (
          <Alert tone="warning">
            范围内有 {plan.unavailableCount} 人离职、冻结或未激活，导入后也不能启用。
          </Alert>
        )}
        <Alert>新成员导入后为待授权状态；已有成员保留角色与启用设置。同步完成后可继续设置角色并启用。</Alert>
      </CardContent>
      <CardFooter className="identity-directory-footer">
        <Button disabled={busy} onClick={onBack}>
          返回选择
        </Button>
        <Button variant="primary" disabled={busy} onClick={onConfirm}>
          {busy ? "正在保存同步结果…" : "确认并同步"}
        </Button>
      </CardFooter>
    </Card>
  );
}
