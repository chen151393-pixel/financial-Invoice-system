// 与后端 identity 模块 VO 一致；角色与权限由后端判定，前端只展示。

export interface RoleItem {
  code: string;
  label: string;
}

export interface SessionUser {
  /** feishu 飞书账号；admin 应急管理员；service 服务身份 */
  kind: "feishu" | "admin" | "service";
  name: string;
  roles: RoleItem[];
  canManageAccess: boolean;
}

export interface SessionInfo {
  authenticated: boolean;
  user?: SessionUser | null;
}

export interface LoginOptions {
  feishu: boolean;
  password: boolean;
}

export interface FeishuOutcome {
  status: "none" | "pending" | "checking" | "success" | "failed";
  reason: string | null;
}

export interface AccessDepartment {
  id: number;
  name: string;
  path: string;
  /** 被直接选为同步范围 */
  inScope: boolean;
  /** 自身或上级部门被选中，成员在同步范围内 */
  covered: boolean;
  roles: string[];
}

export interface AccessUser {
  id: number;
  name: string;
  departments: string[];
  active: boolean;
  inactiveReason: string | null;
  customRoles: boolean;
  personalRoles: string[];
  roles: string[];
  lastLoginAt: string | null;
}

export interface SyncRun {
  id: number;
  trigger: "manual" | "schedule";
  status: "running" | "succeeded" | "failed";
  departments: number;
  usersAdded: number;
  usersUpdated: number;
  usersDeactivated: number;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface AccessOverview {
  feishuConfigured: boolean;
  roles: RoleItem[];
  departments: AccessDepartment[];
  users: AccessUser[];
  lastSync: SyncRun | null;
}
