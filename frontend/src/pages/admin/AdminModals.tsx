import React from "react";
import PermissionModal from "./PermissionModal";
import { AddTagModal, EditTagModal } from "./TagModals";
import type { AdminModalsProps } from "./types";
import {
  AddUserModal,
  ChangePasswordModal,
  EditUserModal,
} from "./UserModals";

const AdminModals: React.FC<AdminModalsProps> = ({
  isAddUserModalOpen,
  setIsAddUserModalOpen,
  newUsername,
  setNewUsername,
  newPassword,
  setNewPassword,
  handleAddUser,
  isPasswordModalOpen,
  closePasswordModal,
  passwordUser,
  changedPassword,
  setChangedPassword,
  changedPasswordConfirmation,
  setChangedPasswordConfirmation,
  isChangingPassword,
  handleChangePassword,
  isEditUserModalOpen,
  setIsEditUserModalOpen,
  selectedUser,
  editRole,
  setEditRole,
  editIsActive,
  setEditIsActive,
  handleUpdateUser,
  isPermissionModalOpen,
  setIsPermissionModalOpen,
  permUserId,
  setPermUserId,
  permContractId,
  setPermContractId,
  permLevel,
  setPermLevel,
  users,
  handleAddPermission,
  isAddTagModalOpen,
  setIsAddTagModalOpen,
  newTagName,
  setNewTagName,
  newTagColor,
  setNewTagColor,
  handleAddTag,
  isEditTagModalOpen,
  setIsEditTagModalOpen,
  selectedTag,
  editTagName,
  setEditTagName,
  editTagColor,
  setEditTagColor,
  handleUpdateTag,
}) => (
  <>
    <AddUserModal
      isOpen={isAddUserModalOpen}
      onClose={() => setIsAddUserModalOpen(false)}
      onSubmit={handleAddUser}
      username={newUsername}
      setUsername={setNewUsername}
      password={newPassword}
      setPassword={setNewPassword}
    />
    <ChangePasswordModal
      isOpen={isPasswordModalOpen}
      onClose={closePasswordModal}
      onSubmit={handleChangePassword}
      user={passwordUser}
      password={changedPassword}
      setPassword={setChangedPassword}
      confirmation={changedPasswordConfirmation}
      setConfirmation={setChangedPasswordConfirmation}
      isChanging={isChangingPassword}
    />
    <EditUserModal
      isOpen={isEditUserModalOpen}
      onClose={() => setIsEditUserModalOpen(false)}
      onSubmit={handleUpdateUser}
      user={selectedUser}
      role={editRole}
      setRole={setEditRole}
      isActive={editIsActive}
      setIsActive={setEditIsActive}
    />
    <PermissionModal
      isOpen={isPermissionModalOpen}
      onClose={() => setIsPermissionModalOpen(false)}
      onSubmit={handleAddPermission}
      userId={permUserId}
      setUserId={setPermUserId}
      contractId={permContractId}
      setContractId={setPermContractId}
      level={permLevel}
      setLevel={setPermLevel}
      users={users}
    />
    <AddTagModal
      isOpen={isAddTagModalOpen}
      onClose={() => setIsAddTagModalOpen(false)}
      onSubmit={handleAddTag}
      name={newTagName}
      setName={setNewTagName}
      color={newTagColor}
      setColor={setNewTagColor}
    />
    <EditTagModal
      isOpen={isEditTagModalOpen}
      onClose={() => setIsEditTagModalOpen(false)}
      onSubmit={handleUpdateTag}
      tag={selectedTag}
      name={editTagName}
      setName={setEditTagName}
      color={editTagColor}
      setColor={setEditTagColor}
    />
  </>
);

export default AdminModals;
