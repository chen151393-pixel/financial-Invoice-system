import { AccessPage } from "../modules/identity/pages/AccessPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

/** 人员与权限：飞书部门、同步范围、角色；仅系统管理员。 */
export default function AccessWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="access"
      onNavigate={navigate}
      title="人员与权限"
      description="人员与部门以飞书为准；在这里选择同步范围并分配角色"
      meta={[{ label: "数据来源", value: "飞书通讯录" }]}
    >
      <AccessPage />
    </AppFrame>
  );
}
