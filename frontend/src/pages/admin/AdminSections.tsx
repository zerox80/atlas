import React from "react";
import { motion } from "framer-motion";
import {
  FiAlertTriangle,
  FiArchive,
  FiCheck,
  FiDownload,
  FiEdit2,
  FiLoader,
  FiLock,
  FiPlus,
  FiShield,
  FiTag,
  FiTrash2,
  FiUsers,
  FiX,
} from "react-icons/fi";
import type { AdminTab, Permission, Tag, User } from "./types";

interface AdminSectionsProps {
  activeTab: AdminTab;
  setActiveTab: (tab: AdminTab) => void;
  users: User[];
  permissions: Permission[];
  tags: Tag[];
  setIsAddUserModalOpen: (isOpen: boolean) => void;
  openEditUser: (user: User) => void;
  handleDeleteUser: (user: User) => void;
  setIsPermissionModalOpen: (isOpen: boolean) => void;
  handleDeletePermission: (permissionId: number) => void;
  getLevelColor: (level: string) => string;
  getLevelLabel: (level: string) => string;
  setIsAddTagModalOpen: (isOpen: boolean) => void;
  openEditTag: (tag: Tag) => void;
  handleDeleteTag: (tagId: number) => void;
  backupError: string | null;
  isBackupRunning: boolean;
  handleBackup: () => void;
}

const AdminSections: React.FC<AdminSectionsProps> = ({
  activeTab,
  setActiveTab,
  users,
  permissions,
  tags,
  setIsAddUserModalOpen,
  openEditUser,
  handleDeleteUser,
  setIsPermissionModalOpen,
  handleDeletePermission,
  getLevelColor,
  getLevelLabel,
  setIsAddTagModalOpen,
  openEditTag,
  handleDeleteTag,
  backupError,
  isBackupRunning,
  handleBackup,
}) => (
  <>
    {/* Tabs */}
    <div className="surface mb-6 flex flex-wrap gap-1 p-1.5">
      <button
        onClick={() => setActiveTab("users")}
        className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
          activeTab === "users"
            ? "bg-white/[0.09] text-white"
            : "text-white/38 hover:bg-white/[0.04] hover:text-white"
        }`}
      >
        <FiUsers />
        Benutzer ({users.length})
      </button>
      <button
        onClick={() => setActiveTab("permissions")}
        className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
          activeTab === "permissions"
            ? "bg-white/[0.09] text-white"
            : "text-white/38 hover:bg-white/[0.04] hover:text-white"
        }`}
      >
        <FiLock />
        Berechtigungen ({permissions.length})
      </button>
      <button
        onClick={() => setActiveTab("tags")}
        className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
          activeTab === "tags"
            ? "bg-white/[0.09] text-white"
            : "text-white/38 hover:bg-white/[0.04] hover:text-white"
        }`}
      >
        <FiTag />
        Tags ({tags.length})
      </button>
      <button
        onClick={() => setActiveTab("backup")}
        className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
          activeTab === "backup"
            ? "bg-white/[0.09] text-white"
            : "text-white/38 hover:bg-white/[0.04] hover:text-white"
        }`}
      >
        <FiArchive />
        Datensicherung
      </button>
    </div>

    {/* Users Tab */}
    {activeTab === "users" && (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        <div className="flex justify-end">
          <button
            onClick={() => setIsAddUserModalOpen(true)}
            className="btn-primary"
          >
            <FiPlus /> Neuer Benutzer
          </button>
        </div>

        <div className="surface overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Benutzer
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Rolle
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Status
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">2FA</th>
                <th className="text-right p-4 text-gray-400 font-medium">
                  Aktionen
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr
                  key={user.id}
                  className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors"
                >
                  <td className="p-4">
                    <span className="text-white font-medium">
                      {user.username}
                    </span>
                  </td>
                  <td className="p-4">
                    <span
                      className={`px-2 py-1 rounded text-sm ${
                        user.role === "admin"
                          ? "bg-purple-500/20 text-purple-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
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
                  <td className="p-4 text-right space-x-2">
                    <button
                      onClick={() => openEditUser(user)}
                      className="p-2 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                      title="Bearbeiten"
                    >
                      <FiEdit2 />
                    </button>
                    <button
                      onClick={() => handleDeleteUser(user)}
                      className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
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
    )}

    {/* Permissions Tab */}
    {activeTab === "permissions" && (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        <div className="flex justify-end">
          <button
            onClick={() => setIsPermissionModalOpen(true)}
            className="btn-primary"
          >
            <FiPlus /> Berechtigung hinzufügen
          </button>
        </div>

        <div className="surface overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Benutzer
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Vertrag
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Berechtigung
                </th>
                <th className="text-right p-4 text-gray-400 font-medium">
                  Aktionen
                </th>
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
                permissions.map((perm) => (
                  <tr
                    key={perm.id}
                    className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="p-4 text-white">{perm.username}</td>
                    <td className="p-4 text-gray-300">{perm.contract_title}</td>
                    <td className="p-4">
                      <span
                        className={`px-2 py-1 rounded text-sm ${getLevelColor(perm.permission_level)}`}
                      >
                        {getLevelLabel(perm.permission_level)}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <button
                        onClick={() => handleDeletePermission(perm.id)}
                        className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
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
    )}

    {/* Tags Tab */}
    {activeTab === "tags" && (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        <div className="flex justify-end">
          <button
            onClick={() => setIsAddTagModalOpen(true)}
            className="btn-primary"
          >
            <FiPlus /> Neuer Tag
          </button>
        </div>

        <div className="surface overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Farbe
                </th>
                <th className="text-left p-4 text-gray-400 font-medium">
                  Name
                </th>
                <th className="text-right p-4 text-gray-400 font-medium">
                  Aktionen
                </th>
              </tr>
            </thead>
            <tbody>
              {tags.length === 0 ? (
                <tr>
                  <td colSpan={3} className="p-8 text-center text-gray-500">
                    Keine Tags vorhanden
                  </td>
                </tr>
              ) : (
                tags.map((tag) => (
                  <tr
                    key={tag.id}
                    className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors"
                  >
                    <td className="p-4">
                      <div
                        className="w-8 h-8 rounded-lg border-2 border-gray-600"
                        style={{ backgroundColor: tag.color }}
                      />
                    </td>
                    <td className="p-4">
                      <span
                        className="px-3 py-1 rounded-full text-sm font-medium"
                        style={{
                          backgroundColor: `${tag.color}20`,
                          color: tag.color,
                        }}
                      >
                        {tag.name}
                      </span>
                    </td>
                    <td className="p-4 text-right space-x-2">
                      <button
                        onClick={() => openEditTag(tag)}
                        className="p-2 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                        title="Bearbeiten"
                      >
                        <FiEdit2 />
                      </button>
                      <button
                        onClick={() => handleDeleteTag(tag.id)}
                        className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                        title="Löschen"
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
    )}

    {/* Backup Tab */}
    {activeTab === "backup" && (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="surface overflow-hidden"
      >
        <div className="grid gap-8 p-6 lg:grid-cols-[1fr_0.8fr] lg:p-8">
          <div>
            <div
              className={[
                "mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border",
                "border-[#b8f15a]/20 bg-[#b8f15a]/10 text-xl text-[#b8f15a]",
              ].join(" ")}
            >
              <FiArchive />
            </div>
            <p className="eyebrow">Vollständiger Dokumentexport</p>
            <h2 className="mt-3 text-2xl font-semibold text-white">
              Verträge und Rechnungen sichern
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-white/50">
              Erstellt eine ZIP mit allen Verträgen und Rechnungen. Für jeden
              Datensatz enthält sie eine lesbare Info-PDF sowie die hinterlegte
              Originaldatei, sofern diese auf dem Server verfügbar ist.
            </p>

            <ul className="mt-6 space-y-3 text-sm text-white/55">
              <li className="flex items-start gap-3">
                <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" />{" "}
                Geschützte Dokumente werden ebenfalls gesichert.
              </li>
              <li className="flex items-start gap-3">
                <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" /> Fehlende
                Dateien werden im Sicherungsbericht aufgeführt.
              </li>
              <li className="flex items-start gap-3">
                <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" />{" "}
                Benutzerkonten und die vollständige Datenbank sind nicht
                enthalten.
              </li>
            </ul>
          </div>

          <div className="flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-black/20 p-5">
            <div>
              <div
                className={[
                  "flex items-start gap-3 rounded-xl border border-amber-400/20",
                  "bg-amber-400/[0.07] p-4 text-amber-100/80",
                ].join(" ")}
              >
                <FiAlertTriangle className="mt-0.5 shrink-0 text-amber-300" />
                <p className="text-sm leading-5">
                  Die ZIP enthält vertrauliche Daten und ist nicht
                  passwortgeschützt. Legen Sie sie ausschließlich an einem
                  geschützten Ort ab.
                </p>
              </div>

              {backupError && (
                <div
                  role="alert"
                  className="mt-4 rounded-xl border border-red-400/20 bg-red-500/[0.08] p-4 text-sm text-red-200"
                >
                  {backupError}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={handleBackup}
              disabled={isBackupRunning}
              aria-busy={isBackupRunning}
              className="btn-primary mt-6 w-full justify-center disabled:cursor-wait disabled:opacity-60"
            >
              {isBackupRunning ? (
                <FiLoader className="animate-spin" />
              ) : (
                <FiDownload />
              )}
              {isBackupRunning ? "Sicherung wird erstellt …" : "Alles sichern"}
            </button>
          </div>
        </div>
      </motion.div>
    )}
  </>
);

export default AdminSections;
