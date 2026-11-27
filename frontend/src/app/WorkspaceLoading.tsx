import { Skeleton } from "../shared/components/ui";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import type { View } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

/** 页面代码下载期间保留导航，用户可以直接继续切换菜单。 */
export function WorkspaceLoading({ view, label }: { view: View; label: string }) {
  const navigateView = useViewNavigate();
  return (
    <AppFrame groups={navigation} activeId={view} onNavigate={navigateView} title={label}>
      <Skeleton rows={5} label={`正在加载${label}…`} />
    </AppFrame>
  );
}
