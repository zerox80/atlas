import { useCallback, useEffect, useRef, useState } from "react";
import api from "../../api";
import type { Permission, PermissionPage, Tag, User } from "./types";

const PERMISSION_PAGE_SIZE = 50;

export const useAdminData = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [permissionTotal, setPermissionTotal] = useState(0);
  const [permissionPage, setPermissionPage] = useState(0);
  const [tags, setTags] = useState<Tag[]>([]);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [permissionsLoaded, setPermissionsLoaded] = useState(false);
  const [tagsLoaded, setTagsLoaded] = useState(false);
  const [permissionsLoading, setPermissionsLoading] = useState(false);
  const [usersError, setUsersError] = useState(false);
  const [permissionsError, setPermissionsError] = useState(false);
  const [tagsError, setTagsError] = useState(false);
  const permissionRequest = useRef<AbortController | null>(null);

  const loadUsers = useCallback(async () => {
    setUsersError(false);
    try {
      const response = await api.get<User[]>("/admin/users");
      setUsers(response.data);
    } catch {
      setUsersError(true);
    } finally {
      setUsersLoaded(true);
    }
  }, []);

  const loadTags = useCallback(async () => {
    setTagsError(false);
    try {
      const response = await api.get<Tag[]>("/tags");
      setTags(response.data);
    } catch {
      setTagsError(true);
    } finally {
      setTagsLoaded(true);
    }
  }, []);

  const loadPermissions = useCallback(async () => {
    const controller = new AbortController();
    permissionRequest.current?.abort();
    permissionRequest.current = controller;
    setPermissionsLoading(true);
    setPermissionsError(false);
    try {
      const response = await api.get<PermissionPage>("/admin/permissions", {
        params: {
          offset: permissionPage * PERMISSION_PAGE_SIZE,
          limit: PERMISSION_PAGE_SIZE,
        },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;

      const lastPage = Math.max(
        0,
        Math.ceil(response.data.total / PERMISSION_PAGE_SIZE) - 1,
      );
      if (permissionPage > lastPage) {
        setPermissionPage(lastPage);
        return;
      }
      setPermissions(response.data.items);
      setPermissionTotal(response.data.total);
    } catch {
      if (!controller.signal.aborted) setPermissionsError(true);
    } finally {
      if (permissionRequest.current === controller) {
        setPermissionsLoaded(true);
        setPermissionsLoading(false);
        permissionRequest.current = null;
      }
    }
  }, [permissionPage]);

  const loadData = useCallback(
    async () => {
      await Promise.all([loadUsers(), loadPermissions(), loadTags()]);
    },
    [loadPermissions, loadTags, loadUsers],
  );

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    void loadTags();
  }, [loadTags]);

  useEffect(() => {
    void loadPermissions();
    return () => {
      permissionRequest.current?.abort();
      permissionRequest.current = null;
    };
  }, [loadPermissions]);

  const failedResources = [
    usersError ? "Benutzer" : null,
    permissionsError ? "Berechtigungen" : null,
    tagsError ? "Tags" : null,
  ].filter((resource): resource is string => resource !== null);
  const loadError = failedResources.length
    ? `${failedResources.join(", ")} konnten nicht geladen werden.`
    : null;

  return {
    isLoading: !usersLoaded || !permissionsLoaded || !tagsLoaded,
    loadData,
    loadError,
    loadPermissions,
    loadTags,
    loadUsers,
    permissionPage,
    permissionPageSize: PERMISSION_PAGE_SIZE,
    permissionTotal,
    permissions,
    permissionsLoading,
    setPermissionPage,
    tags,
    users,
  };
};
