import { useNavigate } from "react-router";
import { paths } from "../../../app/paths";
import { Tabs } from "../../../shared/components/ui";

export function SupplierTabs({ value }: { value: "profiles" | "owners" }) {
  const navigate = useNavigate();
  return (
    <Tabs
      label="供应商档案视图"
      items={[
        { key: "profiles", label: "供应商档案" },
        { key: "owners", label: "人员关联" },
      ]}
      value={value}
      onChange={(key) => void navigate(key === "owners" ? paths.supplierOwners : paths.supplierGroups)}
    />
  );
}
