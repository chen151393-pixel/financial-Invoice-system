# 连接状态面板与认证API

`api.ts`维护该功能的请求与响应类型；`components/`负责渲染和收集输入。组合页面位于 `web/app/WorkspacePage.tsx`，公共Button、Panel、JsonView和请求封装来自shared。

校验、JSON输入解析和是否可执行均交给Python后端；Hook只管理UI/请求状态。复用现有控件，不复制业务算法或样式。当前接口类型人工维护，尚未从OpenAPI生成。

验证：`npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build`。涉及组件外观时检查正式入口与较窄窗口，不能只凭构建结果认定视觉通过。
