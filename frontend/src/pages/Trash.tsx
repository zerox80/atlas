import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import { PageHeader } from "../components/ui";
import { getListIdFromSearchParams } from "../features/documents/documentUtils";
import TrashBrowser from "../features/trash/TrashBrowser";
import { queryKeys } from "../queryKeys";
import type { ContractList } from "../types";

const Trash: React.FC = () => {
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);
  const { data: workspaces = [] } = useQuery<ContractList[]>(
    queryKeys.lists,
    async () => (await api.get<ContractList[]>("/lists")).data,
    { staleTime: 60_000 },
  );
  const workspace = workspaces.find((item) => item.id === listId);
  const workspaceName = workspace?.is_default
    ? `Workspace${workspace.owner_username ? ` · ${workspace.owner_username}` : ""}`
    : workspace?.name;

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Workspace / Wiederherstellung"
        title={workspaceName ? `Papierkorb · ${workspaceName}` : "Papierkorb"}
        description="Gelöschte Verträge und Rechnungen dieses Workspaces wiederherstellen oder dauerhaft entfernen."
      />
      <TrashBrowser listId={listId} />
    </div>
  );
};

export default Trash;
