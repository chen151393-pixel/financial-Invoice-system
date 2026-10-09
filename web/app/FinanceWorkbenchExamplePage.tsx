import { FinanceWorkbenchExample } from "../modules/reconciliation/example/FinanceWorkbenchExample";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";

export default function FinanceWorkbenchExamplePage() {
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={(target) => location.assign(viewPath(target))}
      title="财务核对闭环示例"
      subtitle="沿用当前报关审核、发票导入和行匹配入口，预览财务每日处理路径。"
      mode="demo"
      dataLabel="方案示例 · 不保存业务数据"
      actions={
        <a className="ui-button ui-button--secondary" href="/finance-reconciliation">
          返回正式财务核对
        </a>
      }
      notice="示例编号、金额和状态仅用于演示，不调用 NS、柠檬云或保存接口。正式业务入口和待实现能力在各视图中分别标明。"
    >
      <FinanceWorkbenchExample />
    </AppFrame>
  );
}
