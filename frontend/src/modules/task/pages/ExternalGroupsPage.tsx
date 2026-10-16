import { useState } from "react";
import { useSearchParams } from "react-router";
import { ExternalGroupCatalog } from "../components/ExternalGroupCatalog";
import { GroupImportPreview } from "../components/GroupImportPreview";
import { GroupImportUpload } from "../components/GroupImportUpload";
import "./task.css";
import "./supplier-groups.css";
import "./external-groups.css";
export function ExternalGroupsPage() {
  const [params, setParams] = useSearchParams();
  const importId = params.get("importId");
  const [message, setMessage] = useState("");
  return (
    <div className="it-page sg-page eg-page">
      {message && (
        <p className="sg-feedback" role="status">
          {message}
        </p>
      )}
      {importId ? (
        <GroupImportPreview
          key={importId}
          importId={importId}
          onClose={() => setParams({})}
          onDone={(text) => {
            setMessage(text);
            setParams({});
          }}
        />
      ) : (
        <>
          <GroupImportUpload
            onPreview={(id) => {
              setMessage("");
              setParams({ importId: id });
            }}
          />
          <ExternalGroupCatalog />
        </>
      )}
    </div>
  );
}
