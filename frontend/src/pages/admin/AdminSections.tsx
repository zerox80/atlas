import React from "react";
import AdminTabs from "./AdminTabs";
import BackupSection from "./BackupSection";
import PermissionsSection from "./PermissionsSection";
import TagsSection from "./TagsSection";
import type { AdminTab, Permission, Tag, User } from "./types";
import UsersSection from "./UsersSection";

interface AdminSectionsProps {
  activeTab: AdminTab;
  backupError: string | null;
  getLevelColor: (level: string) => string;
  getLevelLabel: (level: string) => string;
  handleBackup: () => void;
  handleDeletePermission: (permissionId: number) => void;
  handleDeleteTag: (tagId: number) => void;
  handleDeleteUser: (user: User) => void;
  isBackupRunning: boolean;
  openEditTag: (tag: Tag) => void;
  openEditUser: (user: User) => void;
  openPasswordModal: (user: User) => void;
  permissions: Permission[];
  setActiveTab: (tab: AdminTab) => void;
  setIsAddTagModalOpen: (isOpen: boolean) => void;
  setIsAddUserModalOpen: (isOpen: boolean) => void;
  setIsPermissionModalOpen: (isOpen: boolean) => void;
  tags: Tag[];
  users: User[];
}

const AdminSections: React.FC<AdminSectionsProps> = ({
  activeTab,
  backupError,
  getLevelColor,
  getLevelLabel,
  handleBackup,
  handleDeletePermission,
  handleDeleteTag,
  handleDeleteUser,
  isBackupRunning,
  openEditTag,
  openEditUser,
  openPasswordModal,
  permissions,
  setActiveTab,
  setIsAddTagModalOpen,
  setIsAddUserModalOpen,
  setIsPermissionModalOpen,
  tags,
  users,
}) => (
  <>
    <AdminTabs
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      userCount={users.length}
      permissionCount={permissions.length}
      tagCount={tags.length}
    />
    {activeTab === "users" && (
      <UsersSection
        users={users}
        onAddUser={() => setIsAddUserModalOpen(true)}
        onEditUser={openEditUser}
        onOpenPasswordModal={openPasswordModal}
        onDeleteUser={handleDeleteUser}
      />
    )}
    {activeTab === "permissions" && (
      <PermissionsSection
        permissions={permissions}
        getLevelColor={getLevelColor}
        getLevelLabel={getLevelLabel}
        onAddPermission={() => setIsPermissionModalOpen(true)}
        onDeletePermission={handleDeletePermission}
      />
    )}
    {activeTab === "tags" && (
      <TagsSection
        tags={tags}
        onAddTag={() => setIsAddTagModalOpen(true)}
        onEditTag={openEditTag}
        onDeleteTag={handleDeleteTag}
      />
    )}
    {activeTab === "backup" && (
      <BackupSection
        error={backupError}
        isRunning={isBackupRunning}
        onBackup={handleBackup}
      />
    )}
  </>
);

export default AdminSections;
