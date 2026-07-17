import { useEffect, useState } from "react";
import { Command } from "cmdk";
import {
  FiArrowRight,
  FiCalendar,
  FiFileText,
  FiFolder,
  FiSearch,
} from "react-icons/fi";
import { useNavigate } from "react-router-dom";
import api from "../api";
import type { Contract } from "../types";

const CommandPalette = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [contracts, setContracts] = useState<Contract[]>([]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    const externalOpen = () => setOpen(true);
    document.addEventListener("keydown", handleKey);
    window.addEventListener("atlas:command", externalOpen);
    return () => {
      document.removeEventListener("keydown", handleKey);
      window.removeEventListener("atlas:command", externalOpen);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    api
      .get<Contract[]>("/contracts", { params: { limit: 50 } })
      .then((response) => setContracts(response.data))
      .catch(() => setContracts([]));
  }, [open]);

  const go = (path: string) => {
    navigate(path);
    setOpen(false);
  };

  const itemClass = [
    "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5",
    "text-sm text-[#b9c1cd] data-[selected=true]:bg-white/[0.07]",
    "data-[selected=true]:text-white",
  ].join(" ");
  const groupClass = [
    "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2",
    "[&_[cmdk-group-heading]]:text-[10px]",
    "[&_[cmdk-group-heading]]:font-bold",
    "[&_[cmdk-group-heading]]:uppercase",
    "[&_[cmdk-group-heading]]:tracking-[.16em]",
    "[&_[cmdk-group-heading]]:text-[#586273]",
  ].join(" ");

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-[65] bg-black/70 backdrop-blur-md"
          onClick={() => setOpen(false)}
        />
      )}
      <Command.Dialog
        open={open}
        onOpenChange={setOpen}
        label="Globale Suche"
        className={[
          "surface-raised fixed left-1/2 top-[14vh] z-[70] w-[calc(100%-2rem)]",
          "max-w-2xl -translate-x-1/2 overflow-hidden p-2",
          "shadow-[0_30px_100px_rgba(0,0,0,.7)]",
        ].join(" ")}
      >
        <div className="flex items-center border-b border-white/[0.07] px-4">
          <FiSearch className="mr-3 text-[#b8f15a]" />
          <Command.Input
            autoFocus
            placeholder="Dokument, Sammlung oder Aktion suchen …"
            className="w-full bg-transparent py-4 text-base text-white placeholder:text-[#606b7b] focus:outline-none"
          />
          <kbd className="rounded-md border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-[10px] text-[#697384]">
            ESC
          </kbd>
        </div>
        <Command.List className="max-h-[55vh] overflow-y-auto p-2">
          <Command.Empty className="py-12 text-center text-sm text-[#727d8d]">
            Keine passenden Ergebnisse.
          </Command.Empty>
          <Command.Group heading="Schnellzugriff" className={groupClass}>
            {[
              {
                label: "Verträge öffnen",
                path: "/contracts",
                icon: FiFileText,
              },
              {
                label: "Rechnungen öffnen",
                path: "/invoices",
                icon: FiFileText,
              },
              { label: "Kalender öffnen", path: "/calendar", icon: FiCalendar },
              { label: "Sammlungen öffnen", path: "/lists", icon: FiFolder },
            ].map(({ label, path, icon: Icon }) => (
              <Command.Item
                key={path}
                value={label}
                onSelect={() => go(path)}
                className={itemClass}
              >
                <Icon className="text-[#7f8a9a]" />
                <span className="flex-1">{label}</span>
                <FiArrowRight className="opacity-40" />
              </Command.Item>
            ))}
          </Command.Group>
          {contracts.length > 0 && (
            <Command.Group
              heading="Dokumente"
              className={`mt-2 border-t border-white/[0.06] pt-2 ${groupClass}`}
            >
              {contracts.map((contract) => (
                <Command.Item
                  key={contract.id}
                  value={`${contract.title} ${contract.description || ""}`}
                  onSelect={() =>
                    go(
                      contract.document_type === "invoice"
                        ? "/invoices"
                        : "/contracts",
                    )
                  }
                  className={itemClass}
                >
                  <span
                    className={[
                      "flex h-8 w-8 items-center justify-center rounded-lg",
                      contract.document_type === "invoice"
                        ? "bg-[#7397ff]/10 text-[#7397ff]"
                        : "bg-[#b8f15a]/10 text-[#b8f15a]",
                    ].join(" ")}
                  >
                    <FiFileText />
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {contract.title}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider text-[#596475]">
                    {contract.document_type === "invoice"
                      ? "Rechnung"
                      : "Vertrag"}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command.Dialog>
    </>
  );
};

export default CommandPalette;
