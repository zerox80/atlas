import { useState } from "react";
import type { FormEventHandler } from "react";
import api from "../../api";
import { getApiErrorMessage } from "../../utils/errorUtils";

type ReloadAdminData = () => Promise<void>;

export const useAdminPermissions = (loadData: ReloadAdminData) => {
  const [isPermissionModalOpen, setIsPermissionModalOpen] = useState(false);
  const [permUserId, setPermUserId] = useState(0);
  const [permContractId, setPermContractId] = useState(0);
  const [permLevel, setPermLevel] = useState("read");

  const handleAddPermission: FormEventHandler<HTMLFormElement> = async (
    event,
  ) => {
    event.preventDefault();
    try {
      await api.post("/admin/permissions", {
        user_id: permUserId,
        contract_id: permContractId,
        permission_level: permLevel,
      });
      setIsPermissionModalOpen(false);
      setPermUserId(0);
      setPermContractId(0);
      setPermLevel("read");
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const handleDeletePermission = async (permissionId: number) => {
    if (!confirm("Berechtigung wirklich entfernen?")) return;
    try {
      await api.delete(`/admin/permissions/${permissionId}`);
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
    permLevel,
    permUserId,
    setIsPermissionModalOpen,
    setPermContractId,
    setPermLevel,
    setPermUserId,
  };
};
