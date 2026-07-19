import React, { useState } from "react";
import { FiShield } from "react-icons/fi";
import { LoadingState, PageHeader } from "../components/ui";
import AdminModals from "./admin/AdminModals";
import AdminSections from "./admin/AdminSections";
import AdminStats from "./admin/AdminStats";
import { getPermissionLevelColor, getPermissionLevelLabel } from "./admin/permissionPresentation";
import type { AdminTab } from "./admin/types";
import { useAdminBackup } from "./admin/useAdminBackup";
import { useAdminData } from "./admin/useAdminData";
import { useAdminPermissions } from "./admin/useAdminPermissions";
import { useAdminTags } from "./admin/useAdminTags";
import { useAdminUsers } from "./admin/useAdminUsers";

const AdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AdminTab>("users");
  const {
    isLoading,
    loadData,
    loadError,
    loadPermissions,
    loadTags,
    loadUsers,
    permissionPage,
    permissionPageSize,
    permissionTotal,
    permissions,
    permissionsLoading,
    setPermissionPage,
    tags,
    users,
  } = useAdminData();
  const backup = useAdminBackup();
  const userManagement = useAdminUsers(loadUsers);
  const permissionManagement = useAdminPermissions(loadPermissions);
  const tagManagement = useAdminTags(loadTags);

  if (isLoading) {
    return <LoadingState label="Administration wird geladen" />;
  }

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="System / Control Center"
        title="Administration"
        description="Benutzer, Dokumentrechte, Taxonomie und Datensicherungen an einem zentralen Kontrollpunkt verwalten."
        actions={
          <span className="chip border-[#b8f15a]/20 bg-[#b8f15a]/[0.07] text-[#b8f15a]">
            <FiShield /> Admin access
          </span>
        }
      />

      {loadError && (
        <div
          role="alert"
          className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.07] px-4 py-3 text-sm text-rose-200"
        >
          <span>{loadError}</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void loadData()}
          >
            Erneut versuchen
          </button>
        </div>
      )}

      <AdminStats
        userCount={users.length}
        activeUserCount={users.filter((user) => user.is_active).length}
        permissionCount={permissionTotal}
        tagCount={tags.length}
      />

      <AdminSections
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        users={users}
        permissions={permissions}
        permissionsLoading={permissionsLoading}
        permissionPage={permissionPage}
        permissionPageSize={permissionPageSize}
        permissionTotal={permissionTotal}
        setPermissionPage={setPermissionPage}
        tags={tags}
        setIsAddUserModalOpen={userManagement.setIsAddUserModalOpen}
        openEditUser={userManagement.openEditUser}
        openPasswordModal={userManagement.openPasswordModal}
        handleDeleteUser={userManagement.handleDeleteUser}
        setIsPermissionModalOpen={permissionManagement.setIsPermissionModalOpen}
        handleDeletePermission={permissionManagement.handleDeletePermission}
        getLevelColor={getPermissionLevelColor}
        getLevelLabel={getPermissionLevelLabel}
        setIsAddTagModalOpen={tagManagement.setIsAddTagModalOpen}
        openEditTag={tagManagement.openEditTag}
        handleDeleteTag={tagManagement.handleDeleteTag}
        backupError={backup.backupError}
        isBackupRunning={backup.isBackupRunning}
        handleBackup={backup.handleBackup}
      />

      <AdminModals
        isAddUserModalOpen={userManagement.isAddUserModalOpen}
        setIsAddUserModalOpen={userManagement.setIsAddUserModalOpen}
        newUsername={userManagement.newUsername}
        setNewUsername={userManagement.setNewUsername}
        newPassword={userManagement.newPassword}
        setNewPassword={userManagement.setNewPassword}
        handleAddUser={userManagement.handleAddUser}
        isPasswordModalOpen={userManagement.isPasswordModalOpen}
        closePasswordModal={userManagement.closePasswordModal}
        passwordUser={userManagement.passwordUser}
        changedPassword={userManagement.changedPassword}
        setChangedPassword={userManagement.setChangedPassword}
        changedPasswordConfirmation={userManagement.changedPasswordConfirmation}
        setChangedPasswordConfirmation={userManagement.setChangedPasswordConfirmation}
        isChangingPassword={userManagement.isChangingPassword}
        handleChangePassword={userManagement.handleChangePassword}
        isEditUserModalOpen={userManagement.isEditUserModalOpen}
        setIsEditUserModalOpen={userManagement.setIsEditUserModalOpen}
        selectedUser={userManagement.selectedUser}
        editRole={userManagement.editRole}
        setEditRole={userManagement.setEditRole}
        editIsActive={userManagement.editIsActive}
        setEditIsActive={userManagement.setEditIsActive}
        handleUpdateUser={userManagement.handleUpdateUser}
        isPermissionModalOpen={permissionManagement.isPermissionModalOpen}
        setIsPermissionModalOpen={permissionManagement.setIsPermissionModalOpen}
        permUserId={permissionManagement.permUserId}
        setPermUserId={permissionManagement.setPermUserId}
        permContractId={permissionManagement.permContractId}
        setPermContractId={permissionManagement.setPermContractId}
        permLevel={permissionManagement.permLevel}
        setPermLevel={permissionManagement.setPermLevel}
        users={users}
        handleAddPermission={permissionManagement.handleAddPermission}
        isAddTagModalOpen={tagManagement.isAddTagModalOpen}
        setIsAddTagModalOpen={tagManagement.setIsAddTagModalOpen}
        newTagName={tagManagement.newTagName}
        setNewTagName={tagManagement.setNewTagName}
        newTagColor={tagManagement.newTagColor}
        setNewTagColor={tagManagement.setNewTagColor}
        handleAddTag={tagManagement.handleAddTag}
        isEditTagModalOpen={tagManagement.isEditTagModalOpen}
        setIsEditTagModalOpen={tagManagement.setIsEditTagModalOpen}
        selectedTag={tagManagement.selectedTag}
        editTagName={tagManagement.editTagName}
        setEditTagName={tagManagement.setEditTagName}
        editTagColor={tagManagement.editTagColor}
        setEditTagColor={tagManagement.setEditTagColor}
        handleUpdateTag={tagManagement.handleUpdateTag}
      />
    </div>
  );
};

export default AdminPanel;
