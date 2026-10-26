import { UiKitShowcase } from "../shared/components/ui/showcase/UiKitShowcase";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

/** 统一组件库展示页：演示全部组件与组合方式，数据为虚构演示数据。 */
export default function UiKitWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame groups={navigation} activeId="ui-kit" onNavigate={navigate} title="界面组件库">
      <UiKitShowcase />
    </AppFrame>
  );
}
