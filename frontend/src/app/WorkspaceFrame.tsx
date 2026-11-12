import { AppFrame as Frame } from "../shared/components/AppFrame";
import { SessionMenu } from "../modules/identity/SessionMenu";
import { useSession } from "../modules/identity/session-context";

/**
 * 在应用装配层注入身份操作，公共框架不依赖业务模块。
 * 菜单按后端页面权限过滤，空分组不展示；接口仍由后端校验。
 */
export function AppFrame<Id extends string>(props: Parameters<typeof Frame<Id>>[0]) {
  const { user } = useSession();
  const groups = props.groups
    .map((group) => ({ ...group, items: group.items.filter((item) => user?.pages?.includes(item.id)) }))
    .filter((group) => group.items.length > 0);
  return <Frame {...props} groups={groups} sessionActions={<SessionMenu />} />;
}
