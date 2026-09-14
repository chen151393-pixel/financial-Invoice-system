# 旧界面演示

演示页面与真实 PL 核对共用导航、页头和内容框架；当前页明确显示数据来源。`DemoApp.tsx` 负责入口装配与 URL 导航，`web/app/navigation.tsx` 维护全站菜单，复用 `web/shared/components/AppFrame.tsx` 与 Sidebar。七个业务演示页面仍使用 `fixtures.ts` 的虚构列表，`components/SourceHealth.tsx` 提供共用展示。

PL 菜单已改为打开正式页面 `/pl-reconciliation`。Vite 主应用兼容旧 `/demo?view=pl` 地址并转到正式入口。该页面只在用户提交查询后，通过后端真实读取 NS；说明见 [核对模块](../../web/modules/reconciliation/README.md)。已移除旧 PL 模拟页面、数据文件、场景控件和静态 Excel，避免与真实结果混淆。

其他演示页面仍通过 `web/app/DemoPage.tsx` 按需加载原型 CSS 和数据，演示按钮不操作 NS。`app/page.tsx` 保留旧 Vinext 原型入口，独立原型构建不承载真实 API；实际 PL 查询请启动本项目 Vite 和 Python 后端。

原型维护运行 `npm.cmd run test:prototype`；正式前端构建和类型检查也覆盖其导入。

进项发票列表使用 6 条演示样本，搜索与状态筛选组合生效，标签数量随搜索结果更新；底部展示实际匹配数量，无结果时可清除筛选。顶部金额卡片是全量模拟概览，不代表样本统计。异常行按状态进入异常处理页。搜索框和备注框提供可见键盘焦点；上述交互不调用真实业务接口。
