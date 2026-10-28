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
  openDepartmentId: string;
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
  enabled: boolean;
  directoryActive: boolean;
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
  /** 新后端返回有已导入员工的部门；旧版本缺失时兼容展示 departments。 */
  importedDepartments?: AccessDepartment[];
  users: AccessUser[];
  lastSync: SyncRun | null;
}

export interface DirectorySelection {
  departmentIds: string[];
  userIds: string[];
}
export interface PreviewDepartment {
  id: string;
  name: string;
  path: string;
  depth: number;
  memberCount: number;
}
export interface DirectoryPreview {
  id: string;
  expiresAt: string;
  departments: PreviewDepartment[];
  selection: DirectorySelection;
}
export interface PreviewMember {
  id: string;
  name: string;
  departments: string[];
  selected: boolean;
  selectable: boolean;
  reason: string | null;
  imported: boolean;
  coveredByDepartment: boolean;
}
export interface DirectoryMembers {
  items: PreviewMember[];
  total: number;
  page: number;
  pageSize: number;
  selectedCount: number;
  coveredDepartmentIds: string[];
}
export interface DirectoryPlan {
  selection: DirectorySelection;
  selectedCount: number;
  addedCount: number;
  retainedCount: number;
  removedNames: string[];
  departmentNames: string[];
  userNames: string[];
  unavailableCount: number;
}
export interface UserList {
  items: AccessUser[];
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
}
