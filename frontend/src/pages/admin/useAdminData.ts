import { useCallback, useEffect, useState } from "react";
import api, { fetchAllContracts } from "../../api";
import type { Contract, Permission, Tag, User } from "./types";

export const useAdminData = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [usersResponse, contractsResponse, permissionsResponse, tagsResponse] =
        await Promise.all([
          api.get<User[]>("/admin/users"),
          fetchAllContracts(),
          api.get<Permission[]>("/admin/permissions"),
          api.get<Tag[]>("/tags"),
        ]);
      setUsers(usersResponse.data);
      setContracts(contractsResponse);
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

  return { contracts, isLoading, loadData, permissions, tags, users };
};
