import { AppFrame as Frame } from "../shared/components/AppFrame";
import { SessionMenu } from "../modules/identity/SessionMenu";

/** 在应用装配层注入身份操作，公共框架不依赖业务模块。 */
export function AppFrame<Id extends string>(props: Parameters<typeof Frame<Id>>[0]) {
  return <Frame {...props} sessionActions={<SessionMenu />} />;
}
