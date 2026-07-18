import React from "react";
import { FiArchive, FiLock, FiTag, FiUsers } from "react-icons/fi";
import type { AdminTab } from "./types";

interface AdminTabsProps {
  activeTab: AdminTab;
  permissionCount: number;
  setActiveTab: (tab: AdminTab) => void;
  tagCount: number;
  userCount: number;
}

const tabButtonClassName = (isActive: boolean) =>
  [
    "flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors",
    isActive
      ? "bg-white/[0.09] text-white"
      : "text-white/38 hover:bg-white/[0.04] hover:text-white",
  ].join(" ");

const AdminTabs: React.FC<AdminTabsProps> = ({
  activeTab,
  permissionCount,
  setActiveTab,
  tagCount,
  userCount,
}) => (
  <div className="surface mb-6 flex flex-wrap gap-1 p-1.5">
    <button
      onClick={() => setActiveTab("users")}
      className={tabButtonClassName(activeTab === "users")}
    >
      <FiUsers />
      Benutzer ({userCount})
    </button>
    <button
      onClick={() => setActiveTab("permissions")}
      className={tabButtonClassName(activeTab === "permissions")}
    >
      <FiLock />
      Berechtigungen ({permissionCount})
    </button>
    <button
      onClick={() => setActiveTab("tags")}
      className={tabButtonClassName(activeTab === "tags")}
    >
      <FiTag />
      Tags ({tagCount})
    </button>
    <button
      onClick={() => setActiveTab("backup")}
      className={tabButtonClassName(activeTab === "backup")}
    >
      <FiArchive />
      Datensicherung
    </button>
  </div>
);

export default AdminTabs;
