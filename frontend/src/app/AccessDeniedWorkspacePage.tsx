import { Link } from "react-router";
import { useSession } from "../modules/identity/session-context";
import { Card, CardContent, CardHeader, EmptyState } from "../shared/components/ui";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { viewPath } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function AccessDeniedWorkspacePage() {
  const { user } = useSession();
  const navigate = useViewNavigate();
  const items = navigation.flatMap((group) => group.items).filter((item) => user?.pages?.includes(item.id));
  return (
    <AppFrame<string>
      groups={navigation}
      activeId=""
      onNavigate={(id) => {
        const item = items.find((entry) => entry.id === id);
        if (item) navigate(item.id);
      }}
      title="暂无访问权限"
      description="当前角色未获得此页面的访问权限，请联系系统管理员调整授权"
    >
      <Card>
        <CardHeader title="可访问页面" />
        <CardContent>
          {items.length ? (
            <ul>
              {items.map((item) => (
                <li key={item.id}>
                  <Link to={viewPath(item.id)}>{item.label}</Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="尚未分配可访问页面"
              description="你的账号已登录，请联系系统管理员为角色勾选页面。"
            />
          )}
        </CardContent>
      </Card>
    </AppFrame>
  );
}
