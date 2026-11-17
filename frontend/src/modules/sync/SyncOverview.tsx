import { SyncHealthGrid } from "./components/SyncHealthGrid";
import { SyncRecords } from "./components/SyncRecords";
import { SyncSourceCards } from "./components/SyncSourceCards";
import { useSyncRecords } from "./hooks/useSyncRecords";
import "./components/sync-background.css";
import "./components/sync-layout.css";

export function SyncOverview() {
  const records = useSyncRecords();
  return (
    <>
      <SyncSourceCards plan={records.plans?.lemon ?? null} nsPlan={records.plans?.ns ?? null} />
      <SyncHealthGrid />
      <SyncRecords state={records} />
    </>
  );
}
