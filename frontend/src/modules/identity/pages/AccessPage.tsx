import { Button, ErrorState, Skeleton } from "../../../shared/components/ui";
import { DepartmentCard } from "../components/DepartmentCard";
import { SyncCard } from "../components/SyncCard";
import { UserCard } from "../components/UserCard";
import { useAccess } from "../hooks/useAccess";
import "./access.css";

/** 人员与权限：飞书同步、同步范围与部门角色、人员个人角色；仅系统管理员可用，后端校验。 */
export function AccessPage() {
  const { data, error, loading, reload } = useAccess();

  if (!data) {
    return loading ? (
      <Skeleton rows={6} label="正在读取人员与权限" />
    ) : (
      <ErrorState
        title="人员与权限读取失败"
        message={error}
        action={<Button onClick={() => void reload()}>重新读取</Button>}
      />
    );
  }

  return (
    <div className="identity-access-page">
      {error && (
        <ErrorState
          title="刷新失败，以下为上一次读取的结果"
          message={error}
          action={<Button onClick={() => void reload()}>重新读取</Button>}
        />
      )}
      <SyncCard configured={data.feishuConfigured} lastSync={data.lastSync} onDone={reload} />
      <DepartmentCard
        departments={data.departments}
        roles={data.roles}
        lastSyncId={data.lastSync?.id ?? null}
        onSaved={reload}
      />
      <UserCard users={data.users} roles={data.roles} onSaved={reload} />
    </div>
  );
}
