import { useCallback, useEffect, useState } from "react";
import api from "../../api";
import type { Permission, Tag, User } from "./types";

export const useAdminData = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [usersResponse, permissionsResponse, tagsResponse] =
        await Promise.all([
          api.get<User[]>("/admin/users"),
          api.get<Permission[]>("/admin/permissions"),
          api.get<Tag[]>("/tags"),
        ]);
      setUsers(usersResponse.data);
      setPermissions(permissionsResponse.data);
      setTags(tagsResponse.data);
    } catch (error) {
      console.error("Failed to load admin data:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return { isLoading, loadData, permissions, tags, users };
};
