export interface User {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
  has_2fa: boolean;
  default_workspace_id: number | null;
  default_workspace_name: string | null;
}

export interface Permission {
  id: number;
  user_id: number;
  scope_type: "document" | "workspace";
  contract_id?: number | null;
  list_id?: number | null;
  permission_level: string;
  username: string;
  contract_title?: string | null;
  list_name?: string | null;
  target_name?: string | null;
}

export interface DefaultWorkspaceOption {
  id: number;
  name: string;
  owner_user_id: number | null;
  owner_username: string | null;
  is_personal: boolean;
  requires_write_grant: boolean;
}

export interface PermissionPage {
  items: Permission[];
  total: number;
  offset: number;
  limit: number;
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
  editDefaultWorkspaceId: number;
  setEditDefaultWorkspaceId: (value: number) => void;
  defaultWorkspaceOptions: DefaultWorkspaceOption[];
  defaultWorkspacesLoading: boolean;
  handleUpdateUser: React.FormEventHandler<HTMLFormElement>;
  isPermissionModalOpen: boolean;
  setIsPermissionModalOpen: (isOpen: boolean) => void;
  permUserId: number;
  setPermUserId: (value: number) => void;
  permContractId: number;
  setPermContractId: (value: number) => void;
  permListId: number;
  setPermListId: (value: number) => void;
  permScope: "workspace" | "document";
  setPermScope: (value: "workspace" | "document") => void;
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
