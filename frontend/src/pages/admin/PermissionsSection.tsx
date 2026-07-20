import React from "react";
import { motion } from "framer-motion";
import {
  FiChevronLeft,
  FiChevronRight,
  FiPlus,
  FiTrash2,
} from "react-icons/fi";
import type { Permission } from "./types";

interface PermissionsSectionProps {
  getLevelColor: (level: string) => string;
  getLevelLabel: (level: string) => string;
  loading: boolean;
  onAddPermission: () => void;
  onDeletePermission: (permission: Permission) => void;
  onPageChange: (page: number) => void;
  page: number;
  pageSize: number;
  permissions: Permission[];
  total: number;
}

const PermissionsSection: React.FC<PermissionsSectionProps> = ({
  getLevelColor,
  getLevelLabel,
  loading,
  onAddPermission,
  onDeletePermission,
  onPageChange,
  page,
  pageSize,
  permissions,
  total,
}) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="space-y-4"
  >
    <div className="flex justify-end">
      <button onClick={onAddPermission} className="btn-primary">
        <FiPlus /> Berechtigung hinzufügen
      </button>
    </div>

    <div className="surface overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-900/50">
          <tr>
            <th className="p-4 text-left font-medium text-gray-400">Benutzer</th>
            <th className="p-4 text-left font-medium text-gray-400">
              Workspace / Dokument
            </th>
            <th className="p-4 text-left font-medium text-gray-400">
              Berechtigung
            </th>
            <th className="p-4 text-right font-medium text-gray-400">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={4} className="p-8 text-center text-gray-500">
                Berechtigungen werden geladen …
              </td>
            </tr>
          ) : permissions.length === 0 ? (
            <tr>
              <td colSpan={4} className="p-8 text-center text-gray-500">
                Keine Berechtigungen vorhanden
              </td>
            </tr>
          ) : (
            permissions.map((permission) => (
              <tr
                key={`${permission.scope_type}-${permission.id}`}
                className="border-t border-gray-700 transition-colors hover:bg-gray-800/50"
              >
                <td className="p-4 text-white">{permission.username}</td>
                <td className="p-4 text-gray-300">
                  <div>{permission.target_name || "—"}</div>
                  <span className="mt-1 inline-block text-[10px] font-bold uppercase tracking-[0.12em] text-gray-500">
                    {permission.scope_type === "workspace"
                      ? "Workspace"
                      : "Dokument-Ausnahme"}
                  </span>
                </td>
                <td className="p-4">
                  <span
                    className={`rounded px-2 py-1 text-sm ${getLevelColor(permission.permission_level)}`}
                  >
                    {getLevelLabel(permission.permission_level)}
                  </span>
                </td>
                <td className="p-4 text-right">
                  <button
                    onClick={() => onDeletePermission(permission)}
                    className="rounded p-2 text-red-400 transition-colors hover:bg-red-500/20"
                    title="Entfernen"
                  >
                    <FiTrash2 />
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      <div className="flex items-center justify-between gap-4 border-t border-gray-700 px-4 py-3 text-sm text-gray-400">
        <span>
          {total === 0
            ? "0 Berechtigungen"
            : `${page * pageSize + 1}–${Math.min(total, (page + 1) * pageSize)} von ${total}`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            className="icon-btn"
            aria-label="Vorherige Berechtigungsseite"
            disabled={loading || page === 0}
            onClick={() => onPageChange(page - 1)}
          >
            <FiChevronLeft />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label="Nächste Berechtigungsseite"
            disabled={loading || (page + 1) * pageSize >= total}
            onClick={() => onPageChange(page + 1)}
          >
            <FiChevronRight />
          </button>
        </div>
      </div>
    </div>
  </motion.div>
);

export default PermissionsSection;
