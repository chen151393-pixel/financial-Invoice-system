import { useNavigate } from "react-router";
import { paths } from "../../../app/paths";
import { Tabs } from "../../../shared/components/ui";

export function AccessTabs({ value }: { value: "people" | "roles" }) {
  const navigate = useNavigate();
  return (
    <Tabs
      label="人员与权限视图"
      items={[
        { key: "people", label: "人员授权" },
        { key: "roles", label: "角色管理" },
      ]}
      value={value}
      onChange={(key) => void navigate(key === "roles" ? paths.rolePages : paths.access)}
    />
  );
}
