import React from "react";

interface AdminStatsProps {
  activeUserCount: number;
  permissionCount: number;
  tagCount: number;
  userCount: number;
}

const AdminStats: React.FC<AdminStatsProps> = ({
  activeUserCount,
  permissionCount,
  tagCount,
  userCount,
}) => (
  <div className="mb-5 grid gap-3 sm:grid-cols-3">
    <div className="surface p-5">
      <p className="eyebrow">Benutzer</p>
      <p className="metric-value mt-3">{userCount}</p>
      <p className="mt-2 text-xs text-white/34">{activeUserCount} aktiv</p>
    </div>
    <div className="surface p-5">
      <p className="eyebrow">Freigaben</p>
      <p className="metric-value mt-3">{permissionCount}</p>
      <p className="mt-2 text-xs text-white/34">Dokumentbezogene Rechte</p>
    </div>
    <div className="surface p-5">
      <p className="eyebrow">Taxonomie</p>
      <p className="metric-value mt-3">{tagCount}</p>
      <p className="mt-2 text-xs text-white/34">Verfügbare Tags</p>
    </div>
  </div>
);

export default AdminStats;
