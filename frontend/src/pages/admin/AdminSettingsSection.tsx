import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FiEye, FiEyeOff, FiSettings } from "react-icons/fi";
import { useSearchParams } from "react-router-dom";
import api from "../../api";
import { useUser } from "../../App";
import { invalidateListAndDocumentQueries } from "../../queryKeys";
import { getApiErrorMessage } from "../../utils/errorUtils";

interface WorkspaceVisibilityResponse {
  show_other_user_workspaces: boolean;
}

const AdminSettingsSection: React.FC = () => {
  const { user, setUser } = useUser();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const showOtherUserWorkspaces =
    user?.show_other_user_workspaces !== false;

  const toggleWorkspaceVisibility = async () => {
    if (!user || isSaving) return;
    const nextValue = !showOtherUserWorkspaces;
    setIsSaving(true);
    setError(null);
    try {
      const response = await api.put<WorkspaceVisibilityResponse>(
        "/admin/preferences/workspace-visibility",
        { show_other_user_workspaces: nextValue },
      );
      setUser({
        ...user,
        show_other_user_workspaces:
          response.data.show_other_user_workspaces,
      });
      if (!response.data.show_other_user_workspaces) {
        const nextParams = new URLSearchParams(searchParams);
        nextParams.delete("list_id");
        setSearchParams(nextParams, { replace: true });
      }
      await invalidateListAndDocumentQueries(queryClient);
    } catch (caughtError: unknown) {
      setError(
        getApiErrorMessage(
          caughtError,
          "Die Workspace-Ansicht konnte nicht gespeichert werden.",
        ),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const VisibilityIcon = showOtherUserWorkspaces ? FiEye : FiEyeOff;

  return (
    <section className="surface overflow-hidden">
      <div className="border-b border-white/[0.07] p-5 sm:p-6">
        <p className="eyebrow">Accountgebundene Einstellungen</p>
        <div className="mt-2 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#77a7ff]/20 bg-[#77a7ff]/10 text-[#9dbdff]">
            <FiSettings />
          </span>
          <div>
            <h2 className="section-title">Workspace-Ansicht</h2>
            <p className="mt-1 text-sm muted">
              Diese Einstellung wird in deinem Benutzerkonto gespeichert.
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="flex min-w-0 items-start gap-3">
          <VisibilityIcon className="mt-0.5 shrink-0 text-[#b8f15a]" />
          <div>
            <h3 className="font-semibold text-white">
              Workspaces anderer Benutzer anzeigen
            </h3>
            <p className="mt-1 max-w-2xl text-sm leading-6 muted">
              Blendet persönliche Standard-Workspaces anderer Benutzer in der
              Workspace-Auswahl und in Dokument-Zuordnungen ein oder aus.
              Gemeinsame Team-Workspaces und deine Admin-Rechte bleiben
              unverändert.
            </p>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={showOtherUserWorkspaces}
          aria-label="Workspaces anderer Benutzer anzeigen"
          onClick={() => void toggleWorkspaceVisibility()}
          disabled={isSaving}
          className={[
            "relative h-8 w-14 shrink-0 rounded-full border transition disabled:opacity-50",
            showOtherUserWorkspaces
              ? "border-[#b8f15a]/45 bg-[#b8f15a]/25"
              : "border-white/[0.12] bg-white/[0.06]",
          ].join(" ")}
        >
          <span
            className={[
              "absolute left-0 top-1 h-6 w-6 rounded-full bg-white shadow transition-transform",
              showOtherUserWorkspaces ? "translate-x-6" : "translate-x-1",
            ].join(" ")}
          />
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="border-t border-rose-400/15 bg-rose-400/[0.06] px-5 py-3 text-sm text-rose-200 sm:px-6"
        >
          {error}
        </div>
      )}
    </section>
  );
};

export default AdminSettingsSection;
