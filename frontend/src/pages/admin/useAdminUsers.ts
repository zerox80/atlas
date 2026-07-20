import { useEffect, useRef, useState } from "react";
import type { FormEventHandler } from "react";
import api from "../../api";
import { getApiErrorMessage } from "../../utils/errorUtils";
import type { DefaultWorkspaceOption, User } from "./types";

type ReloadAdminData = () => Promise<void>;

export const useAdminUsers = (loadData: ReloadAdminData) => {
  const [isAddUserModalOpen, setIsAddUserModalOpen] = useState(false);
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [editRole, setEditRole] = useState("user");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editDefaultWorkspaceId, setEditDefaultWorkspaceId] = useState(0);
  const [defaultWorkspaceOptions, setDefaultWorkspaceOptions] = useState<
    DefaultWorkspaceOption[]
  >([]);
  const [defaultWorkspacesLoading, setDefaultWorkspacesLoading] =
    useState(false);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<User | null>(null);
  const [changedPassword, setChangedPassword] = useState("");
  const [changedPasswordConfirmation, setChangedPasswordConfirmation] =
    useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const changePasswordRequestPending = useRef(false);
  const adminPanelMounted = useRef(true);
  const defaultWorkspaceRequest = useRef(0);

  useEffect(() => {
    adminPanelMounted.current = true;
    return () => {
      adminPanelMounted.current = false;
    };
  }, []);

  const handleAddUser: FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    try {
      await api.post("/admin/users", {
        username: newUsername,
        password: newPassword,
      });
      setNewUsername("");
      setNewPassword("");
      setIsAddUserModalOpen(false);
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const clearPasswordModal = () => {
    setIsPasswordModalOpen(false);
    setPasswordUser(null);
    setChangedPassword("");
    setChangedPasswordConfirmation("");
  };

  const openPasswordModal = (user: User) => {
    if (changePasswordRequestPending.current) return;
    setPasswordUser(user);
    setChangedPassword("");
    setChangedPasswordConfirmation("");
    setIsPasswordModalOpen(true);
  };

  const closePasswordModal = () => {
    if (changePasswordRequestPending.current) return;
    clearPasswordModal();
  };

  const handleChangePassword: FormEventHandler<HTMLFormElement> = async (
    event,
  ) => {
    event.preventDefault();
    if (!passwordUser || changePasswordRequestPending.current) return;
    if (changedPassword !== changedPasswordConfirmation) {
      alert("Die eingegebenen Passwörter stimmen nicht überein.");
      return;
    }

    const username = passwordUser.username;
    changePasswordRequestPending.current = true;
    setIsChangingPassword(true);
    try {
      await api.put(`/admin/users/${passwordUser.id}/password`, {
        password: changedPassword,
      });
      if (!adminPanelMounted.current) return;
      clearPasswordModal();
      alert(`Das Passwort für „${username}“ wurde geändert.`);
    } catch (error: unknown) {
      if (adminPanelMounted.current) {
        alert(getApiErrorMessage(error, "Fehler beim Ändern des Passworts"));
      }
    } finally {
      changePasswordRequestPending.current = false;
      if (adminPanelMounted.current) setIsChangingPassword(false);
    }
  };

  const openEditUser = (user: User) => {
    setSelectedUser(user);
    setEditRole(user.role);
    setEditIsActive(user.is_active);
    setEditDefaultWorkspaceId(user.default_workspace_id ?? 0);
    setDefaultWorkspaceOptions([]);
    setIsEditUserModalOpen(true);
    const requestId = defaultWorkspaceRequest.current + 1;
    defaultWorkspaceRequest.current = requestId;
    setDefaultWorkspacesLoading(true);
    void api
      .get<DefaultWorkspaceOption[]>(
        `/admin/users/${user.id}/default-workspace-options`,
      )
      .then((response) => {
        if (
          adminPanelMounted.current &&
          defaultWorkspaceRequest.current === requestId
        ) {
          setDefaultWorkspaceOptions(response.data);
        }
      })
      .catch((error: unknown) => {
        if (
          adminPanelMounted.current &&
          defaultWorkspaceRequest.current === requestId
        ) {
          alert(
            getApiErrorMessage(
              error,
              "Standard-Workspaces konnten nicht geladen werden",
            ),
          );
        }
      })
      .finally(() => {
        if (
          adminPanelMounted.current &&
          defaultWorkspaceRequest.current === requestId
        ) {
          setDefaultWorkspacesLoading(false);
        }
      });
  };

  const handleUpdateUser: FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (!selectedUser) return;
    try {
      await api.put(`/admin/users/${selectedUser.id}`, {
        role: editRole,
        is_active: editIsActive,
      });
      await api.put(
        `/admin/users/${selectedUser.id}/default-workspace`,
        { list_id: editDefaultWorkspaceId || null },
      );
      setIsEditUserModalOpen(false);
      setSelectedUser(null);
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Aktualisieren"));
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (
      !confirm(
        `Benutzer „${user.username}“ wirklich dauerhaft löschen? Dieser Vorgang kann nicht rückgängig gemacht werden.`,
      )
    ) {
      return;
    }
    try {
      await api.delete(`/admin/users/${user.id}`);
      await loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  return {
    changedPassword,
    changedPasswordConfirmation,
    closePasswordModal,
    editIsActive,
    editDefaultWorkspaceId,
    editRole,
    defaultWorkspaceOptions,
    defaultWorkspacesLoading,
    handleAddUser,
    handleChangePassword,
    handleDeleteUser,
    handleUpdateUser,
    isAddUserModalOpen,
    isChangingPassword,
    isEditUserModalOpen,
    isPasswordModalOpen,
    newPassword,
    newUsername,
    openEditUser,
    openPasswordModal,
    passwordUser,
    selectedUser,
    setChangedPassword,
    setChangedPasswordConfirmation,
    setEditIsActive,
    setEditDefaultWorkspaceId,
    setEditRole,
    setIsAddUserModalOpen,
    setIsEditUserModalOpen,
    setNewPassword,
    setNewUsername,
  };
};
