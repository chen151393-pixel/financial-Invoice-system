# 旧界面演示

这是独立的模拟原型，不是正式业务实现。`DemoApp.tsx`负责导航，`pages/`按七个视图拆分，`fixtures.ts`保存模拟列表，`components/SourceHealth.tsx`提供共用展示。

正式入口通过 `web/app/DemoPage.tsx` 按需加载本目录及原型CSS；`app/page.tsx`只保留旧Vinext入口转发。原型中的本地金额、筛选和模拟提示仍供演示，正式业务不得复用这些规则；后续每个业务模块接入后，以后端计算和持久状态替换对应演示页，再移除相关fixtures。

原型维护运行 `npm.cmd run test:prototype`；正式前端构建和类型检查也覆盖其导入是否有效。
