import React from "react";
import ModalFrame from "./ModalFrame";
import type { User } from "./types";

interface AddUserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  password: string;
  setPassword: (value: string) => void;
  setUsername: (value: string) => void;
  username: string;
}

export const AddUserModal: React.FC<AddUserModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  password,
  setPassword,
  setUsername,
  username,
}) => (
  <ModalFrame isOpen={isOpen} onClose={onClose}>
    <h2 className="mb-4 text-xl font-bold text-white">Neuer Benutzer</h2>
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-400">
          Benutzername
        </label>
        <input
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
          required
          minLength={3}
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-400">
          Passwort
        </label>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
          required
          minLength={8}
        />
      </div>
      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500"
        >
          Erstellen
        </button>
      </div>
    </form>
  </ModalFrame>
);

interface ChangePasswordModalProps {
  confirmation: string;
  isChanging: boolean;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  password: string;
  setConfirmation: (value: string) => void;
  setPassword: (value: string) => void;
  user: User | null;
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({
  confirmation,
  isChanging,
  isOpen,
  onClose,
  onSubmit,
  password,
  setConfirmation,
  setPassword,
  user,
}) => {
  if (!user) return null;

  return (
    <ModalFrame
      isOpen={isOpen}
      onClose={isChanging ? undefined : onClose}
      overlayClassName="p-4"
      contentClassName="max-h-[calc(100vh-2rem)] overflow-y-auto"
      ariaBusy={isChanging}
      ariaLabelledBy="change-password-title"
    >
      <h2
        id="change-password-title"
        className="mb-2 text-xl font-bold text-white"
      >
        Passwort ändern
      </h2>
      <p className="mb-4 text-sm text-gray-400">
        Neues Passwort für <span className="font-medium text-white">{user.username}</span>{" "}
        ({user.role === "admin" ? "Admin" : "Benutzer"})
      </p>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="changed-password"
            className="mb-1 block text-sm font-medium text-gray-400"
          >
            Neues Passwort
          </label>
          <input
            id="changed-password"
            name="changed-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
            disabled={isChanging}
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            aria-describedby="changed-password-hint"
            autoFocus
          />
          <p id="changed-password-hint" className="mt-1 text-xs text-gray-500">
            Mindestens 8 Zeichen.
          </p>
        </div>
        <div>
          <label
            htmlFor="changed-password-confirmation"
            className="mb-1 block text-sm font-medium text-gray-400"
          >
            Neues Passwort bestätigen
          </label>
          <input
            id="changed-password-confirmation"
            name="changed-password-confirmation"
            type="password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
            disabled={isChanging}
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
          />
        </div>
        {user.has_2fa && (
          <p className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-xs leading-5 text-blue-200">
            Die Zwei-Faktor-Authentifizierung dieses Kontos bleibt aktiv.
          </p>
        )}
        <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs leading-5 text-amber-200">
          Mit der Passwortänderung werden alle bereits aktiven Sitzungen
          ungültig.
        </p>
        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isChanging}
            className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            disabled={isChanging}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500"
          >
            {isChanging ? "Wird geändert …" : "Passwort ändern"}
          </button>
        </div>
      </form>
    </ModalFrame>
  );
};

interface EditUserModalProps {
  isActive: boolean;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  role: string;
  setIsActive: (value: boolean) => void;
  setRole: (value: string) => void;
  user: User | null;
}

export const EditUserModal: React.FC<EditUserModalProps> = ({
  isActive,
  isOpen,
  onClose,
  onSubmit,
  role,
  setIsActive,
  setRole,
  user,
}) => {
  if (!user) return null;

  return (
    <ModalFrame isOpen={isOpen} onClose={onClose}>
      <h2 className="mb-4 text-xl font-bold text-white">
        Benutzer bearbeiten: {user.username}
      </h2>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-400">
            Rolle
          </label>
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className={[
              "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
              "text-white focus:border-blue-500 focus:outline-none",
            ].join(" ")}
          >
            <option value="user">Benutzer</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div>
          <label className="flex cursor-pointer items-center gap-3 text-gray-400">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
              className="h-5 w-5 rounded border-gray-700 bg-gray-800 text-blue-500 focus:ring-blue-500"
            />
            Benutzer ist aktiv
          </label>
        </div>
        <div className="flex gap-3 pt-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500"
          >
            Speichern
          </button>
        </div>
      </form>
    </ModalFrame>
  );
};
