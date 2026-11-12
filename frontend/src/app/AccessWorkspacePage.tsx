import { AccessPage } from "../modules/identity/pages/AccessPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

/** 人员与权限：飞书部门、同步范围、角色；按后端返回的页面权限开放。 */
export default function AccessWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="access"
      onNavigate={navigate}
      title="人员与权限"
      description="管理成员角色，配置各角色可访问的页面"
      meta={[{ label: "数据来源", value: "飞书通讯录" }]}
    >
      <AccessPage />
    </AppFrame>
  );
}
