// 仅供演示页切换场景；不调用通知服务，不代表真实发送结果。
export const notificationScenes = {
  missing: {
    label: "未绑定企微外部群",
    description: "合同已保存到共享盘，尚未绑定供应商企微外部群。",
    next: "绑定外部群后准备通知，由采购人员在企微确认发送。",
    action: "绑定企微外部群",
    tone: "attention",
  },
  queued: {
    label: "待创建通知",
    description: "合同与外部群绑定已齐备，可准备员工发送任务。",
    next: "系统创建任务后仍需员工在企微确认；接口未接入时可手动发送后登记。",
    action: "查看通知",
    tone: "normal",
  },
  sending: {
    label: "创建通知中",
    description: "正在创建员工发送任务，尚未向供应商群发送消息。",
    next: "等待任务创建结果，期间不重复提交。",
    action: "查看发送进度",
    tone: "normal",
  },
  pending: {
    label: "待员工发送",
    description: "员工发送任务已创建，供应商群尚未收到通知。",
    next: "采购人员需在企微核对目标群与合同，确认发送后再更新结果。",
    action: "查看员工发送任务",
    tone: "normal",
  },
  sent: {
    label: "已发送",
    description: "员工已确认发送，查询结果显示目标群发送成功（示例）。",
    next: "已发送不代表供应商已读或已经开票。",
    action: "查看通知记录",
    tone: "normal",
  },
  recorded: {
    label: "人工登记已发送",
    description: "采购人员已登记在企微手动发送，任务进入等待收票。",
    next: "此记录来自人工登记，未通过企微接口核验，也不代表供应商已读。",
    action: "查看人工登记",
    tone: "normal",
  },
  failed: {
    label: "创建通知失败",
    description: "外部群绑定不可用，员工发送任务未创建成功（示例）。",
    next: "核对外部群绑定后重试创建，合同无需重复获取。",
    action: "处理发送失败",
    tone: "attention",
  },
  unknown: {
    label: "结果待核实",
    description: "发送后未收到明确回执，目前无法确认是否送达。",
    next: "先核实渠道记录，避免供应商收到重复通知。",
    action: "核实发送结果",
    tone: "attention",
  },
} as const;

export type NotificationScene = keyof typeof notificationScenes;
export const supplierNotificationChannel = "企微外部群";
export type SupplierContact = { owner: string; groupName: string };
export type ManualNotificationRecord = SupplierContact & { sentAt: string; note: string; message: string };
export const demoSupplierContact: SupplierContact = {
  owner: "采购对接人（示例）",
  groupName: "供应商开票对接群（示例）",
};
