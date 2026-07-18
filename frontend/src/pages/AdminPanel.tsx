import React, { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FiShield } from "react-icons/fi";
import api, { fetchAllContracts } from "../api";
import {
  getApiErrorDetail,
  getApiErrorMessage,
  getApiErrorResponseData,
} from "../utils/errorUtils";
import { LoadingState, PageHeader } from "../components/ui";
import { triggerBlobDownload } from "../utils/downloadUtils";
import AdminModals from "./admin/AdminModals";
import AdminSections from "./admin/AdminSections";
import type { AdminTab, Contract, Permission, Tag, User } from "./admin/types";
import { invalidateDocumentQueries, queryKeys } from "../queryKeys";

const safeBackupFilename = (candidate?: string): string => {
  const filename = candidate
    ?.split(/[\\/]/)
    .pop()
    // Control characters and reserved Windows filename characters are unsafe in downloads.
    // eslint-disable-next-line no-control-regex
    ?.replace(/[\u0000-\u001f<>:"|?*]/g, "_")
    .trim();
  return filename?.toLowerCase().endsWith(".zip")
    ? filename
    : "atlas-datensicherung.zip";
};

const backupFilenameFromHeader = (contentDisposition?: string): string => {
  if (!contentDisposition) return "atlas-datensicherung.zip";

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch) {
    try {
      return safeBackupFilename(decodeURIComponent(encodedMatch[1].trim()));
    } catch {
      // Fall through to the plain filename variant.
    }
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return safeBackupFilename(filenameMatch?.[1]);
};

const backupErrorMessage = async (error: unknown): Promise<string> => {
  const detail = getApiErrorDetail(error);
  if (typeof detail === "string") return detail;

  const responseData = getApiErrorResponseData(error);
  if (typeof responseData === "string") return responseData;

  if (responseData instanceof Blob) {
    try {
      const payload: unknown = JSON.parse(await responseData.text());
      if (
        typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "string"
      ) {
        return payload.detail;
      }
    } catch {
      // Use the stable message below for non-JSON error bodies.
    }
  }

  return "Datensicherung konnte nicht erstellt werden. Bitte versuchen Sie es erneut.";
};

const AdminPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const [users, setUsers] = useState<User[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<AdminTab>("users");
  const [isBackupRunning, setIsBackupRunning] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);

  // Modal states
  const [isAddUserModalOpen, setIsAddUserModalOpen] = useState(false);
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [isPermissionModalOpen, setIsPermissionModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<User | null>(null);
  const [changedPassword, setChangedPassword] = useState('');
  const [changedPasswordConfirmation, setChangedPasswordConfirmation] =
    useState('');
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const changePasswordRequestPending = React.useRef(false);
  const adminPanelMounted = React.useRef(true);

  // Form states
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [editRole, setEditRole] = useState("user");
  const [editIsActive, setEditIsActive] = useState(true);

  // Permission form
  const [permUserId, setPermUserId] = useState<number>(0);
  const [permContractId, setPermContractId] = useState<number>(0);
  const [permLevel, setPermLevel] = useState<string>("read");

  // Tag states
  const [isAddTagModalOpen, setIsAddTagModalOpen] = useState(false);
  const [isEditTagModalOpen, setIsEditTagModalOpen] = useState(false);
  const [selectedTag, setSelectedTag] = useState<Tag | null>(null);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#3b82f6");
  const [editTagName, setEditTagName] = useState("");
  const [editTagColor, setEditTagColor] = useState("#3b82f6");

  useEffect(() => {
    adminPanelMounted.current = true;
    loadData();
    return () => {
      adminPanelMounted.current = false;
    };
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [usersRes, contractsRes, permsRes, tagsRes] = await Promise.all([
        api.get<User[]>("/admin/users"),
        fetchAllContracts(),
        api.get<Permission[]>("/admin/permissions"),
        api.get<Tag[]>("/tags"),
      ]);
      setUsers(usersRes.data);
      setContracts(contractsRes);
      setPermissions(permsRes.data);
      setTags(tagsRes.data);
    } catch (error) {
      console.error("Failed to load admin data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/admin/users", {
        username: newUsername,
        password: newPassword,
      });
      setNewUsername("");
      setNewPassword("");
      setIsAddUserModalOpen(false);
      loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const clearPasswordModal = () => {
    setIsPasswordModalOpen(false);
    setPasswordUser(null);
    setChangedPassword('');
    setChangedPasswordConfirmation('');
  };

  const openPasswordModal = (user: User) => {
    if (changePasswordRequestPending.current) return;
    setPasswordUser(user);
    setChangedPassword('');
    setChangedPasswordConfirmation('');
    setIsPasswordModalOpen(true);
  };

  const closePasswordModal = () => {
    if (changePasswordRequestPending.current) return;
    clearPasswordModal();
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordUser || changePasswordRequestPending.current) return;
    if (changedPassword !== changedPasswordConfirmation) {
      alert('Die eingegebenen Passwörter stimmen nicht überein.');
      return;
    }

    const username = passwordUser.username;
    changePasswordRequestPending.current = true;
    setIsChangingPassword(true);
    try {
      await api.put('/admin/users/' + passwordUser.id + '/password', {
        password: changedPassword,
      });
      if (!adminPanelMounted.current) return;
      clearPasswordModal();
      alert('Das Passwort für „' + username + '“ wurde geändert.');
    } catch (error: unknown) {
      if (adminPanelMounted.current) {
        alert(getApiErrorMessage(error, 'Fehler beim Ändern des Passworts'));
      }
    } finally {
      changePasswordRequestPending.current = false;
      if (adminPanelMounted.current) setIsChangingPassword(false);
    }
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    try {
      await api.put(`/admin/users/${selectedUser.id}`, {
        role: editRole,
        is_active: editIsActive,
      });
      setIsEditUserModalOpen(false);
      setSelectedUser(null);
      loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Aktualisieren"));
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (
      !confirm(
        `Benutzer „${user.username}“ wirklich dauerhaft löschen? Dieser Vorgang kann nicht rückgängig gemacht werden.`,
      )
    )
      return;
    try {
      await api.delete(`/admin/users/${user.id}`);
      loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  const handleAddPermission = async (e: React.FormEvent) => {
    e.preventDefault();
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
      loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const handleDeletePermission = async (permId: number) => {
    if (!confirm("Berechtigung wirklich entfernen?")) return;
    try {
      await api.delete(`/admin/permissions/${permId}`);
      loadData();
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  const openEditUser = (user: User) => {
    setSelectedUser(user);
    setEditRole(user.role);
    setEditIsActive(user.is_active);
    setIsEditUserModalOpen(true);
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case "full":
        return "text-red-400 bg-red-500/20";
      case "write":
        return "text-yellow-400 bg-yellow-500/20";
      case "read":
        return "text-green-400 bg-green-500/20";
      default:
        return "text-gray-400 bg-gray-500/20";
    }
  };

  const getLevelLabel = (level: string) => {
    switch (level) {
      case "full":
        return "Vollzugriff";
      case "write":
        return "Bearbeiten";
      case "read":
        return "Nur Lesen";
      default:
        return level;
    }
  };

  // Tag handlers
  const handleAddTag = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/tags", {
        name: newTagName,
        color: newTagColor,
      });
      setNewTagName("");
      setNewTagColor("#3b82f6");
      setIsAddTagModalOpen(false);
      await Promise.all([
        queryClient.invalidateQueries(queryKeys.tags),
        loadData(),
      ]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const handleUpdateTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTag) return;
    try {
      await api.put(`/tags/${selectedTag.id}`, {
        name: editTagName,
        color: editTagColor,
      });
      setIsEditTagModalOpen(false);
      setSelectedTag(null);
      await Promise.all([
        queryClient.invalidateQueries(queryKeys.tags),
        invalidateDocumentQueries(queryClient),
        loadData(),
      ]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Aktualisieren"));
    }
  };

  const handleDeleteTag = async (tagId: number) => {
    if (!confirm("Tag wirklich löschen? Er wird von allen Verträgen entfernt."))
      return;
    try {
      await api.delete(`/tags/${tagId}`);
      await Promise.all([
        queryClient.invalidateQueries(queryKeys.tags),
        invalidateDocumentQueries(queryClient),
        loadData(),
      ]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  const openEditTag = (tag: Tag) => {
    setSelectedTag(tag);
    setEditTagName(tag.name);
    setEditTagColor(tag.color);
    setIsEditTagModalOpen(true);
  };

  const handleBackup = async () => {
    const confirmed = window.confirm(
      [
        "Diese Datensicherung enthält alle Verträge und Rechnungen",
        "einschließlich geschützter Dokumente. Die ZIP ist nicht",
        "passwortgeschützt. Jetzt erstellen?",
      ].join(" "),
    );
    if (!confirmed) return;

    setIsBackupRunning(true);
    setBackupError(null);

    try {
      const response = await api.post<Blob>("/admin/backup", undefined, {
        responseType: "blob",
      });
      triggerBlobDownload(
        response.data,
        backupFilenameFromHeader(response.headers?.["content-disposition"]),
      );
    } catch (error: unknown) {
      setBackupError(await backupErrorMessage(error));
    } finally {
      setIsBackupRunning(false);
    }
  };

  if (isLoading) {
    return <LoadingState label="Administration wird geladen" />;
  }

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="System / Control Center"
        title="Administration"
        description={[
          "Benutzer, Dokumentrechte, Taxonomie und Datensicherungen an einem",
          "zentralen Kontrollpunkt verwalten.",
        ].join(" ")}
        actions={
          <span className="chip border-[#b8f15a]/20 bg-[#b8f15a]/[0.07] text-[#b8f15a]">
            <FiShield /> Admin access
          </span>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <div className="surface p-5">
          <p className="eyebrow">Benutzer</p>
          <p className="metric-value mt-3">{users.length}</p>
          <p className="mt-2 text-xs text-white/34">
            {users.filter((user) => user.is_active).length} aktiv
          </p>
        </div>
        <div className="surface p-5">
          <p className="eyebrow">Freigaben</p>
          <p className="metric-value mt-3">{permissions.length}</p>
          <p className="mt-2 text-xs text-white/34">Dokumentbezogene Rechte</p>
        </div>
        <div className="surface p-5">
          <p className="eyebrow">Taxonomie</p>
          <p className="metric-value mt-3">{tags.length}</p>
          <p className="mt-2 text-xs text-white/34">Verfügbare Tags</p>
        </div>
      </div>

      <AdminSections
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        users={users}
        permissions={permissions}
        tags={tags}
        setIsAddUserModalOpen={setIsAddUserModalOpen}
        openEditUser={openEditUser}
        openPasswordModal={openPasswordModal}
        handleDeleteUser={handleDeleteUser}
        setIsPermissionModalOpen={setIsPermissionModalOpen}
        handleDeletePermission={handleDeletePermission}
        getLevelColor={getLevelColor}
        getLevelLabel={getLevelLabel}
        setIsAddTagModalOpen={setIsAddTagModalOpen}
        openEditTag={openEditTag}
        handleDeleteTag={handleDeleteTag}
        backupError={backupError}
        isBackupRunning={isBackupRunning}
        handleBackup={handleBackup}
      />

      <AdminModals
        isAddUserModalOpen={isAddUserModalOpen}
        setIsAddUserModalOpen={setIsAddUserModalOpen}
        newUsername={newUsername}
        setNewUsername={setNewUsername}
        newPassword={newPassword}
        setNewPassword={setNewPassword}
        handleAddUser={handleAddUser}
        isPasswordModalOpen={isPasswordModalOpen}
        closePasswordModal={closePasswordModal}
        passwordUser={passwordUser}
        changedPassword={changedPassword}
        setChangedPassword={setChangedPassword}
        changedPasswordConfirmation={changedPasswordConfirmation}
        setChangedPasswordConfirmation={setChangedPasswordConfirmation}
        isChangingPassword={isChangingPassword}
        handleChangePassword={handleChangePassword}
        isEditUserModalOpen={isEditUserModalOpen}
        setIsEditUserModalOpen={setIsEditUserModalOpen}
        selectedUser={selectedUser}
        editRole={editRole}
        setEditRole={setEditRole}
        editIsActive={editIsActive}
        setEditIsActive={setEditIsActive}
        handleUpdateUser={handleUpdateUser}
        isPermissionModalOpen={isPermissionModalOpen}
        setIsPermissionModalOpen={setIsPermissionModalOpen}
        permUserId={permUserId}
        setPermUserId={setPermUserId}
        permContractId={permContractId}
        setPermContractId={setPermContractId}
        permLevel={permLevel}
        setPermLevel={setPermLevel}
        users={users}
        contracts={contracts}
        handleAddPermission={handleAddPermission}
        isAddTagModalOpen={isAddTagModalOpen}
        setIsAddTagModalOpen={setIsAddTagModalOpen}
        newTagName={newTagName}
        setNewTagName={setNewTagName}
        newTagColor={newTagColor}
        setNewTagColor={setNewTagColor}
        handleAddTag={handleAddTag}
        isEditTagModalOpen={isEditTagModalOpen}
        setIsEditTagModalOpen={setIsEditTagModalOpen}
        selectedTag={selectedTag}
        editTagName={editTagName}
        setEditTagName={setEditTagName}
        editTagColor={editTagColor}
        setEditTagColor={setEditTagColor}
        handleUpdateTag={handleUpdateTag}
      />
    </div>
  );
};

export default AdminPanel;
