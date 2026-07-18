import React from "react";
import { motion } from "framer-motion";
import {
  FiCheck,
  FiEdit2,
  FiKey,
  FiPlus,
  FiShield,
  FiTrash2,
  FiX,
} from "react-icons/fi";
import type { User } from "./types";

interface UsersSectionProps {
  onAddUser: () => void;
  onDeleteUser: (user: User) => void;
  onEditUser: (user: User) => void;
  onOpenPasswordModal: (user: User) => void;
  users: User[];
}

const UsersSection: React.FC<UsersSectionProps> = ({
  onAddUser,
  onDeleteUser,
  onEditUser,
  onOpenPasswordModal,
  users,
}) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="space-y-4"
  >
    <div className="flex justify-end">
      <button onClick={onAddUser} className="btn-primary">
        <FiPlus /> Neuer Benutzer
      </button>
    </div>

    <div className="surface overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-900/50">
          <tr>
            <th className="p-4 text-left font-medium text-gray-400">Benutzer</th>
            <th className="p-4 text-left font-medium text-gray-400">Rolle</th>
            <th className="p-4 text-left font-medium text-gray-400">Status</th>
            <th className="p-4 text-left font-medium text-gray-400">2FA</th>
            <th className="p-4 text-right font-medium text-gray-400">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr
              key={user.id}
              className="border-t border-gray-700 transition-colors hover:bg-gray-800/50"
            >
              <td className="p-4">
                <span className="font-medium text-white">{user.username}</span>
              </td>
              <td className="p-4">
                <span
                  className={[
                    "rounded px-2 py-1 text-sm",
                    user.role === "admin"
                      ? "bg-purple-500/20 text-purple-400"
                      : "bg-gray-500/20 text-gray-400",
                  ].join(" ")}
                >
                  {user.role === "admin" ? "Admin" : "Benutzer"}
                </span>
              </td>
              <td className="p-4">
                {user.is_active ? (
                  <span className="flex items-center gap-1 text-green-400">
                    <FiCheck /> Aktiv
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-red-400">
                    <FiX /> Inaktiv
                  </span>
                )}
              </td>
              <td className="p-4">
                {user.has_2fa ? (
                  <span className="text-green-400">
                    <FiShield />
                  </span>
                ) : (
                  <span className="text-gray-500">—</span>
                )}
              </td>
              <td className="space-x-2 p-4 text-right">
                <button
                  onClick={() => onEditUser(user)}
                  className="rounded p-2 text-blue-400 transition-colors hover:bg-blue-500/20"
                  title="Bearbeiten"
                >
                  <FiEdit2 />
                </button>
                <button
                  type="button"
                  onClick={() => onOpenPasswordModal(user)}
                  className="rounded p-2 text-amber-400 transition-colors hover:bg-amber-500/20"
                  title="Passwort ändern"
                  aria-label={`Passwort für ${user.username} ändern`}
                >
                  <FiKey />
                </button>
                <button
                  onClick={() => onDeleteUser(user)}
                  className="rounded p-2 text-red-400 transition-colors hover:bg-red-500/20"
                  title="Dauerhaft löschen"
                >
                  <FiTrash2 />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </motion.div>
);

export default UsersSection;
