import type { ReactNode } from "react";
import type { UploadModalController } from "./useUploadModal";

interface UploadDetailsFormProps {
  controller: UploadModalController;
}

const FieldLabel = ({ children }: { children: ReactNode }) => (
  <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.14em] text-white/38">
    {children}
  </span>
);

const UploadDetailsForm = ({ controller }: UploadDetailsFormProps) => (
  <section className="p-5 sm:p-7">
    <div className="mb-5 flex items-center justify-between">
      <p className="eyebrow">02 · Details prüfen</p>
      <span className="chip">
        {controller.isInvoice ? "Invoice" : "Contract"}
      </span>
    </div>
    <div className="space-y-5">
      {!controller.isEditing && (
        <label className="block">
          <FieldLabel>Ablage-Workspace</FieldLabel>
          <select
            value={controller.workspaceId || ""}
            onChange={(event) =>
              controller.setWorkspaceId(Number(event.target.value))
            }
            className="field"
            required
            disabled={controller.workspacesLoading}
          >
            <option value="">
              {controller.workspacesLoading
                ? "Workspaces werden geladen …"
                : "Workspace wählen …"}
            </option>
            {controller.writableWorkspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.is_default
                  ? "Persönlicher Workspace"
                  : workspace.name}
                {workspace.owner_username
                  ? ` · ${workspace.owner_username}`
                  : ""}
                {workspace.is_preferred_default ? " (Standard)" : ""}
              </option>
            ))}
          </select>
          {!controller.workspacesLoading &&
            controller.writableWorkspaces.length === 0 && (
              <span className="mt-2 block text-[11px] text-rose-300">
                Kein beschreibbarer Workspace freigegeben. Bitte den Admin
                kontaktieren.
              </span>
            )}
          <span className="mt-2 block text-[11px] text-white/28">
            Dein konfigurierter Standard-Workspace ist vorausgewählt. Ein
            fremder persönlicher Workspace ist nie als Upload-Ziel zulässig.
          </span>
        </label>
      )}
      <label className="block">
        <FieldLabel>
          {controller.isInvoice
            ? "Lieferant / Rechnungstitel"
            : "Vertragstitel"}
        </FieldLabel>
        <input
          type="text"
          value={controller.title}
          onChange={(event) => controller.setTitle(event.target.value)}
          className="field"
          placeholder={
            controller.isInvoice
              ? "z. B. Telekom · Juni 2026"
              : "z. B. Cloud Hosting Enterprise"
          }
          required
        />
      </label>
      <div
        className={`grid gap-4 ${controller.isInvoice ? "" : "sm:grid-cols-2"}`}
      >
        <label className="block">
          <FieldLabel>
            {controller.isInvoice ? "Rechnungsbetrag (€)" : "Gesamtwert (€)"}
          </FieldLabel>
          <input
            type="text"
            value={controller.value}
            onChange={(event) => controller.setValue(event.target.value)}
            placeholder="z. B. 17.100,00"
            className="field"
          />
        </label>
        {!controller.isInvoice && (
          <label className="block">
            <FieldLabel>Jährlicher Preis (€)</FieldLabel>
            <input
              type="text"
              value={controller.annualValue}
              onChange={(event) => controller.setAnnualValue(event.target.value)}
              placeholder="z. B. 2.500,00"
              className="field"
            />
          </label>
        )}
      </div>
      <label className="block">
        <FieldLabel>Beschreibung</FieldLabel>
        <textarea
          value={controller.description}
          onChange={(event) => controller.setDescription(event.target.value)}
          className="field min-h-20 resize-y"
          placeholder="Worum geht es in diesem Dokument?"
          rows={3}
        />
      </label>
      <label className="block">
        <FieldLabel>Tags</FieldLabel>
        <input
          type="text"
          value={controller.tags}
          onChange={(event) => controller.setTags(event.target.value)}
          placeholder="Software, SaaS, 2026"
          className="field"
        />
        <span className="mt-2 block text-[11px] text-white/28">
          Mehrere Tags mit Komma trennen. Unbekannte Tags können nur
          Administratoren anlegen.
        </span>
      </label>
      <div
        className={`grid gap-4 ${controller.isInvoice ? "" : "sm:grid-cols-2"}`}
      >
        <label className="block">
          <FieldLabel>
            {controller.isInvoice ? "Rechnungsdatum" : "Startdatum"}
          </FieldLabel>
          <input
            type="date"
            value={controller.startDate}
            onChange={(event) => controller.setStartDate(event.target.value)}
            className="field [color-scheme:dark]"
          />
        </label>
        {!controller.isInvoice && (
          <label className="block">
            <FieldLabel>Enddatum</FieldLabel>
            <input
              type="date"
              value={controller.endDate}
              onChange={(event) => controller.setEndDate(event.target.value)}
              className="field [color-scheme:dark]"
            />
          </label>
        )}
      </div>
      {!controller.isInvoice && (
        <label className="block">
          <FieldLabel>Kündigungsfrist (Tage)</FieldLabel>
          <input
            type="number"
            min="0"
            value={controller.noticePeriod}
            onChange={(event) => controller.setNoticePeriod(event.target.value)}
            placeholder="30"
            className="field"
          />
        </label>
      )}
    </div>
  </section>
);

export default UploadDetailsForm;
