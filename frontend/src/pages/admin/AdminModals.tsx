import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AdminModalsProps } from "./types";

const AdminModals: React.FC<AdminModalsProps> = ({
  isAddUserModalOpen,
  setIsAddUserModalOpen,
  newUsername,
  setNewUsername,
  newPassword,
  setNewPassword,
  handleAddUser,
  isPasswordModalOpen,
  closePasswordModal,
  passwordUser,
  changedPassword,
  setChangedPassword,
  changedPasswordConfirmation,
  setChangedPasswordConfirmation,
  isChangingPassword,
  handleChangePassword,
  isEditUserModalOpen,
  setIsEditUserModalOpen,
  selectedUser,
  editRole,
  setEditRole,
  editIsActive,
  setEditIsActive,
  handleUpdateUser,
  isPermissionModalOpen,
  setIsPermissionModalOpen,
  permUserId,
  setPermUserId,
  permContractId,
  setPermContractId,
  permLevel,
  setPermLevel,
  users,
  contracts,
  handleAddPermission,
  isAddTagModalOpen,
  setIsAddTagModalOpen,
  newTagName,
  setNewTagName,
  newTagColor,
  setNewTagColor,
  handleAddTag,
  isEditTagModalOpen,
  setIsEditTagModalOpen,
  selectedTag,
  editTagName,
  setEditTagName,
  editTagColor,
  setEditTagColor,
  handleUpdateTag,
}) => (
  <>
    {/* Add User Modal */}
    <AnimatePresence>
      {isAddUserModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setIsAddUserModalOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold text-white mb-4">
              Neuer Benutzer
            </h2>
            <form onSubmit={handleAddUser} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Benutzername
                </label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  required
                  minLength={3}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Passwort
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  required
                  minLength={8}
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsAddUserModalOpen(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Abbrechen
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Erstellen
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Change Password Modal */}
    <AnimatePresence>
      {isPasswordModalOpen && passwordUser && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className='fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm'
          onClick={isChangingPassword ? undefined : closePasswordModal}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className='max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-xl border border-gray-700 bg-gray-900 p-6'
            onClick={(e) => e.stopPropagation()}
            role='dialog'
            aria-modal='true'
            aria-labelledby='change-password-title'
            aria-busy={isChangingPassword}
          >
            <h2
              id='change-password-title'
              className='mb-2 text-xl font-bold text-white'
            >
              Passwort ändern
            </h2>
            <p className='mb-4 text-sm text-gray-400'>
              Neues Passwort für{' '}
              <span className='font-medium text-white'>
                {passwordUser.username}
              </span>{' '}
              ({passwordUser.role === 'admin' ? 'Admin' : 'Benutzer'})
            </p>
            <form onSubmit={handleChangePassword} className='space-y-4'>
              <div>
                <label
                  htmlFor='changed-password'
                  className='mb-1 block text-sm font-medium text-gray-400'
                >
                  Neues Passwort
                </label>
                <input
                  id='changed-password'
                  name='changed-password'
                  type='password'
                  value={changedPassword}
                  onChange={(e) => setChangedPassword(e.target.value)}
                  className='w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none'
                  disabled={isChangingPassword}
                  required
                  minLength={8}
                  maxLength={128}
                  autoComplete='new-password'
                  aria-describedby='changed-password-hint'
                  autoFocus
                />
                <p
                  id='changed-password-hint'
                  className='mt-1 text-xs text-gray-500'
                >
                  Mindestens 8 Zeichen.
                </p>
              </div>
              <div>
                <label
                  htmlFor='changed-password-confirmation'
                  className='mb-1 block text-sm font-medium text-gray-400'
                >
                  Neues Passwort bestätigen
                </label>
                <input
                  id='changed-password-confirmation'
                  name='changed-password-confirmation'
                  type='password'
                  value={changedPasswordConfirmation}
                  onChange={(e) =>
                    setChangedPasswordConfirmation(e.target.value)
                  }
                  className='w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none'
                  disabled={isChangingPassword}
                  required
                  minLength={8}
                  maxLength={128}
                  autoComplete='new-password'
                />
              </div>
              {passwordUser.has_2fa && (
                <p className='rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-xs leading-5 text-blue-200'>
                  Die Zwei-Faktor-Authentifizierung dieses Kontos bleibt aktiv.
                </p>
              )}
              <p className='rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs leading-5 text-amber-200'>
                Bereits aktive Sitzungen bleiben bis zu ihrem Ablauf
                angemeldet.
              </p>
              <div className='flex gap-3 pt-2'>
                <button
                  type='button'
                  onClick={closePasswordModal}
                  disabled={isChangingPassword}
                  className='flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600'
                >
                  Abbrechen
                </button>
                <button
                  type='submit'
                  disabled={isChangingPassword}
                  className='flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500'
                >
                  {isChangingPassword ? 'Wird geändert …' : 'Passwort ändern'}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Edit User Modal */}
    <AnimatePresence>
      {isEditUserModalOpen && selectedUser && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setIsEditUserModalOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold text-white mb-4">
              Benutzer bearbeiten: {selectedUser.username}
            </h2>
            <form onSubmit={handleUpdateUser} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Rolle
                </label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                >
                  <option value="user">Benutzer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="flex items-center gap-3 text-gray-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editIsActive}
                    onChange={(e) => setEditIsActive(e.target.checked)}
                    className="w-5 h-5 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
                  />
                  Benutzer ist aktiv
                </label>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsEditUserModalOpen(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Abbrechen
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Speichern
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Add Permission Modal */}
    <AnimatePresence>
      {isPermissionModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setIsPermissionModalOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold text-white mb-4">
              Berechtigung hinzufügen
            </h2>
            <form onSubmit={handleAddPermission} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Benutzer
                </label>
                <select
                  value={permUserId}
                  onChange={(e) => setPermUserId(Number(e.target.value))}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  required
                >
                  <option value={0}>Benutzer wählen...</option>
                  {users
                    .filter((u) => u.role !== "admin" && u.is_active)
                    .map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.username}
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Vertrag
                </label>
                <select
                  value={permContractId}
                  onChange={(e) => setPermContractId(Number(e.target.value))}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  required
                >
                  <option value={0}>Vertrag wählen...</option>
                  {contracts.map((contract) => (
                    <option key={contract.id} value={contract.id}>
                      {contract.title}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Berechtigung
                </label>
                <select
                  value={permLevel}
                  onChange={(e) => setPermLevel(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                >
                  <option value="read">Nur Lesen</option>
                  <option value="write">Bearbeiten</option>
                  <option value="full">Vollzugriff (inkl. Löschen)</option>
                </select>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsPermissionModalOpen(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Abbrechen
                </button>
                <button
                  type="submit"
                  disabled={permUserId === 0 || permContractId === 0}
                  className={[
                    "flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50",
                    "disabled:cursor-not-allowed text-white rounded-lg transition-colors",
                  ].join(" ")}
                >
                  Hinzufügen
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Add Tag Modal */}
    <AnimatePresence>
      {isAddTagModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setIsAddTagModalOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold text-white mb-4">Neuer Tag</h2>
            <form onSubmit={handleAddTag} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  placeholder="z.B. Software, Legal, HR..."
                  required
                  minLength={1}
                  maxLength={50}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Farbe
                </label>
                <div className="flex gap-3 items-center">
                  <input
                    type="color"
                    value={newTagColor}
                    onChange={(e) => setNewTagColor(e.target.value)}
                    className="w-12 h-12 rounded-lg border-2 border-gray-700 cursor-pointer bg-transparent"
                  />
                  <span
                    className="px-3 py-1 rounded-full text-sm font-medium"
                    style={{
                      backgroundColor: `${newTagColor}20`,
                      color: newTagColor,
                    }}
                  >
                    {newTagName || "Vorschau"}
                  </span>
                </div>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsAddTagModalOpen(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Abbrechen
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Erstellen
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Edit Tag Modal */}
    <AnimatePresence>
      {isEditTagModalOpen && selectedTag && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setIsEditTagModalOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold text-white mb-4">
              Tag bearbeiten
            </h2>
            <form onSubmit={handleUpdateTag} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={editTagName}
                  onChange={(e) => setEditTagName(e.target.value)}
                  className={[
                    "w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg",
                    "text-white focus:outline-none focus:border-blue-500",
                  ].join(" ")}
                  required
                  minLength={1}
                  maxLength={50}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Farbe
                </label>
                <div className="flex gap-3 items-center">
                  <input
                    type="color"
                    value={editTagColor}
                    onChange={(e) => setEditTagColor(e.target.value)}
                    className="w-12 h-12 rounded-lg border-2 border-gray-700 cursor-pointer bg-transparent"
                  />
                  <span
                    className="px-3 py-1 rounded-full text-sm font-medium"
                    style={{
                      backgroundColor: `${editTagColor}20`,
                      color: editTagColor,
                    }}
                  >
                    {editTagName || "Vorschau"}
                  </span>
                </div>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsEditTagModalOpen(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Abbrechen
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Speichern
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  </>
);

export default AdminModals;
