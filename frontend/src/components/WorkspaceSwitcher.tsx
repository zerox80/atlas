import type { FC } from "react";
import { FiChevronDown, FiFolder } from "react-icons/fi";
import type { ContractList } from "../types";

interface WorkspaceSwitcherProps {
  activeWorkspaceId: number | null;
  currentUserId?: number;
  isLoading: boolean;
  onChange: (workspaceId: number | null) => void;
  workspaces: ContractList[];
}

const workspaceOptionLabel = (workspace: ContractList) =>
  [
    workspace.is_default ? "Persönlicher Workspace" : workspace.name,
    workspace.owner_username || null,
    workspace.is_preferred_default ? "Standard" : null,
    workspace.can_write === false ? "Nur Lesen" : null,
  ]
    .filter(Boolean)
    .join(" · ");

const WorkspaceSwitcher: FC<WorkspaceSwitcherProps> = ({
  activeWorkspaceId,
  currentUserId,
  isLoading,
  onChange,
  workspaces,
}) => {
  const activeWorkspace = workspaces.find(
    (workspace) => workspace.id === activeWorkspaceId,
  );
  const activeColor = activeWorkspace?.color || "#b8f15a";

  const workspaceKind = activeWorkspace
    ? activeWorkspace.is_default
      ? activeWorkspace.owner_user_id === currentUserId
        ? "Dein persönlicher Bereich"
        : `Persönlicher Bereich${
            activeWorkspace.owner_username
              ? ` · ${activeWorkspace.owner_username}`
              : ""
          }`
      : activeWorkspace.owner_username
        ? `Team-Bereich · ${activeWorkspace.owner_username}`
        : "Gemeinsamer Team-Bereich"
    : null;
  const contextDescription = activeWorkspace
    ? `${activeWorkspace.contract_count} Dokument${
        activeWorkspace.contract_count === 1 ? "" : "e"
      } · ${workspaceKind}${
        activeWorkspace.is_preferred_default ? " · Standard" : ""
      }${activeWorkspace.can_write === false ? " · Nur Lesen" : ""}`
    : "Dokumente aus allen zugänglichen Bereichen";

  return (
    <div className="mb-5 rounded-2xl border border-white/[0.08] bg-white/[0.035] p-3">
      <label
        htmlFor="active-workspace"
        className="mb-2 block text-[10px] font-bold uppercase tracking-[0.16em] text-[#657080]"
      >
        Aktiver Workspace
      </label>
      <div className="relative flex items-center gap-2.5">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border"
          style={{
            backgroundColor: `${activeColor}16`,
            borderColor: `${activeColor}32`,
            color: activeColor,
          }}
        >
          <FiFolder size={16} />
        </span>
        <select
          id="active-workspace"
          value={activeWorkspaceId ?? ""}
          onChange={(event) =>
            onChange(event.target.value ? Number(event.target.value) : null)
          }
          disabled={isLoading}
          className="min-w-0 flex-1 appearance-none bg-transparent py-1 pr-7 text-sm font-semibold text-white outline-none disabled:opacity-50 [&>option]:bg-[var(--panel)] [&>option]:text-[var(--ink)]"
        >
          <option value="">Alle Workspaces · Übersicht</option>
          {activeWorkspaceId !== null && !activeWorkspace && !isLoading && (
            <option value={activeWorkspaceId}>
              Workspace #{activeWorkspaceId} · nicht verfügbar
            </option>
          )}
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspaceOptionLabel(workspace)}
            </option>
          ))}
        </select>
        <FiChevronDown className="pointer-events-none absolute right-0 text-[#657080]" />
      </div>
      <p className="mt-2 truncate text-[11px] text-[#697384]">
        {isLoading ? "Workspaces werden geladen …" : contextDescription}
      </p>
    </div>
  );
};

export default WorkspaceSwitcher;
