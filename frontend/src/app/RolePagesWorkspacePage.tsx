import { RolePagesPage } from "../modules/identity/pages/RolePagesPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function RolePagesWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="access"
      onNavigate={navigate}
      title="人员与权限"
      description="管理成员角色，配置各角色可访问的页面"
      meta={[{ label: "数据来源", value: "平台权限配置" }]}
    >
      <RolePagesPage />
    </AppFrame>
  );
}
