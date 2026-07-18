export interface User {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
  has_2fa: boolean;
}

export interface Permission {
  id: number;
  user_id: number;
  contract_id: number;
  permission_level: string;
  username: string;
  contract_title: string;
}

export interface Tag {
  id: number;
  name: string;
  color: string;
}

export type AdminTab = "users" | "permissions" | "tags" | "backup";

export interface AdminModalsProps {
  isAddUserModalOpen: boolean;
  setIsAddUserModalOpen: (isOpen: boolean) => void;
  newUsername: string;
  setNewUsername: (value: string) => void;
  newPassword: string;
  setNewPassword: (value: string) => void;
  handleAddUser: React.FormEventHandler<HTMLFormElement>;
  isPasswordModalOpen: boolean;
  closePasswordModal: () => void;
  passwordUser: User | null;
  changedPassword: string;
  setChangedPassword: (value: string) => void;
  changedPasswordConfirmation: string;
  setChangedPasswordConfirmation: (value: string) => void;
  isChangingPassword: boolean;
  handleChangePassword: React.FormEventHandler<HTMLFormElement>;
  isEditUserModalOpen: boolean;
  setIsEditUserModalOpen: (isOpen: boolean) => void;
  selectedUser: User | null;
  editRole: string;
  setEditRole: (value: string) => void;
  editIsActive: boolean;
  setEditIsActive: (value: boolean) => void;
  handleUpdateUser: React.FormEventHandler<HTMLFormElement>;
  isPermissionModalOpen: boolean;
  setIsPermissionModalOpen: (isOpen: boolean) => void;
  permUserId: number;
  setPermUserId: (value: number) => void;
  permContractId: number;
  setPermContractId: (value: number) => void;
  permLevel: string;
  setPermLevel: (value: string) => void;
  users: User[];
  handleAddPermission: React.FormEventHandler<HTMLFormElement>;
  isAddTagModalOpen: boolean;
  setIsAddTagModalOpen: (isOpen: boolean) => void;
  newTagName: string;
  setNewTagName: (value: string) => void;
  newTagColor: string;
  setNewTagColor: (value: string) => void;
  handleAddTag: React.FormEventHandler<HTMLFormElement>;
  isEditTagModalOpen: boolean;
  setIsEditTagModalOpen: (isOpen: boolean) => void;
  selectedTag: Tag | null;
  editTagName: string;
  setEditTagName: (value: string) => void;
  editTagColor: string;
  setEditTagColor: (value: string) => void;
  handleUpdateTag: React.FormEventHandler<HTMLFormElement>;
}
import type React from "react";
