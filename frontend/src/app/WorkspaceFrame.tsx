import { useNavigate } from "react-router";
import { AppFrame as Frame } from "../shared/components/AppFrame";
import { SessionMenu } from "../modules/identity/SessionMenu";
import { useSession } from "../modules/identity/session-context";
import { subViewPath } from "./paths";

/**
 * 在应用装配层注入身份操作，公共框架不依赖业务模块。
 * 菜单按后端页面权限过滤，空分组不展示；接口仍由后端校验。
 * 子页面随所属菜单项的页面权限展示，点击后按 paths.ts 的地址跳转。
 */
export function AppFrame<Id extends string>(props: Parameters<typeof Frame<Id>>[0]) {
  const { user } = useSession();
  const navigate = useNavigate();
  const groups = props.groups
    .map((group) => ({ ...group, items: group.items.filter((item) => user?.pages?.includes(item.id)) }))
    .filter((group) => group.items.length > 0);
  return (
    <Frame
      {...props}
      groups={groups}
      onNavigateChild={(id) => {
        const path = subViewPath(id);
        if (path) void navigate(path);
      }}
      sessionActions={<SessionMenu />}
    />
  );
}
