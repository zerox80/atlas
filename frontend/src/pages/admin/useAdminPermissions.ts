import { useState } from "react";
import type { FormEventHandler } from "react";
import api from "../../api";
import { getApiErrorMessage } from "../../utils/errorUtils";
import type { Permission } from "./types";

type ReloadAdminData = () => Promise<void>;

export const useAdminPermissions = (loadData: ReloadAdminData) => {
  const [isPermissionModalOpen, setIsPermissionModalOpen] = useState(false);
  const [permUserId, setPermUserId] = useState(0);
  const [permContractId, setPermContractId] = useState(0);
  const [permListId, setPermListId] = useState(0);
  const [permScope, setPermScope] = useState<"workspace" | "document">(
    "workspace",
  );
  const [permLevel, setPermLevel] = useState("read");

  const handleAddPermission: FormEventHandler<HTMLFormElement> = async (
    event,
  ) => {
    event.preventDefault();
    try {
      const isWorkspace = permScope === "workspace";
      await api.post(
        isWorkspace ? "/admin/workspace-permissions" : "/admin/permissions",
        {
          user_id: permUserId,
          ...(isWorkspace
            ? { list_id: permListId }
            : { contract_id: permContractId }),
          permission_level: permLevel,
        },
      );
      setIsPermissionModalOpen(false);
      setPermUserId(0);
      setPermContractId(0);
      setPermListId(0);
      setPermScope("workspace");
      setPermLevel("read");
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const handleDeletePermission = async (permission: Permission) => {
    if (!confirm("Berechtigung wirklich entfernen?")) return;
    try {
      const endpoint =
        permission.scope_type === "workspace"
          ? "/admin/workspace-permissions"
          : "/admin/permissions";
      await api.delete(`${endpoint}/${permission.id}`);
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  return {
    handleAddPermission,
    handleDeletePermission,
    isPermissionModalOpen,
    permContractId,
    permListId,
    permLevel,
    permScope,
    permUserId,
    setIsPermissionModalOpen,
    setPermContractId,
    setPermListId,
    setPermLevel,
    setPermScope,
    setPermUserId,
  };
};
