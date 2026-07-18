import React from "react";
import { motion } from "framer-motion";
import { FiPlus, FiTrash2 } from "react-icons/fi";
import type { Permission } from "./types";

interface PermissionsSectionProps {
  getLevelColor: (level: string) => string;
  getLevelLabel: (level: string) => string;
  onAddPermission: () => void;
  onDeletePermission: (permissionId: number) => void;
  permissions: Permission[];
}

const PermissionsSection: React.FC<PermissionsSectionProps> = ({
  getLevelColor,
  getLevelLabel,
  onAddPermission,
  onDeletePermission,
  permissions,
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
            <th className="p-4 text-left font-medium text-gray-400">Vertrag</th>
            <th className="p-4 text-left font-medium text-gray-400">
              Berechtigung
            </th>
            <th className="p-4 text-right font-medium text-gray-400">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {permissions.length === 0 ? (
            <tr>
              <td colSpan={4} className="p-8 text-center text-gray-500">
                Keine Berechtigungen vorhanden
              </td>
            </tr>
          ) : (
            permissions.map((permission) => (
              <tr
                key={permission.id}
                className="border-t border-gray-700 transition-colors hover:bg-gray-800/50"
              >
                <td className="p-4 text-white">{permission.username}</td>
                <td className="p-4 text-gray-300">{permission.contract_title}</td>
                <td className="p-4">
                  <span
                    className={`rounded px-2 py-1 text-sm ${getLevelColor(permission.permission_level)}`}
                  >
                    {getLevelLabel(permission.permission_level)}
                  </span>
                </td>
                <td className="p-4 text-right">
                  <button
                    onClick={() => onDeletePermission(permission.id)}
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
    </div>
  </motion.div>
);

export default PermissionsSection;
