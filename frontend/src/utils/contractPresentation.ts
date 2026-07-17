import { FiAlertTriangle, FiCheckCircle, FiClock } from "react-icons/fi";
import type { IconType } from "react-icons";
import type { Contract } from "../types";

const DEFAULT_NOTICE_PERIOD = 30;

export type ContractStateKey = "active" | "attention" | "expired";

export interface ContractState {
  key: ContractStateKey;
  label: string;
  deadline: string;
  tone: string;
  icon: IconType;
}

export const formatContractDate = (value?: string | null): string =>
  value ? new Date(value).toLocaleDateString("de-DE") : "Offen";

export const getCancellationDeadline = (contract: Contract): Date | null => {
  if (!contract.end_date) return null;
  const deadline = new Date(contract.end_date);
  deadline.setDate(
    deadline.getDate() - (contract.notice_period ?? DEFAULT_NOTICE_PERIOD),
  );
  return deadline;
};

export const getContractState = (contract: Contract): ContractState => {
  if (!contract.end_date) {
    return {
      key: "active",
      label: "Unbefristet",
      deadline: "Keine feste Laufzeit",
      tone: "text-[#77a7ff] bg-[#77a7ff]/10 border-[#77a7ff]/15",
      icon: FiCheckCircle,
    };
  }

  const end = new Date(contract.end_date);
  const deadline = getCancellationDeadline(contract)!;
  const now = new Date();
  const days = Math.ceil((deadline.getTime() - now.getTime()) / 86_400_000);

  if (end < now) {
    return {
      key: "expired",
      label: "Abgelaufen",
      deadline: `Endete am ${formatContractDate(contract.end_date)}`,
      tone: "text-[#7d8796] bg-white/[0.04] border-white/[0.07]",
      icon: FiClock,
    };
  }

  if (days <= 30) {
    return {
      key: "attention",
      label: days < 0 ? "Frist verpasst" : `${days} Tage`,
      deadline: `Kündbar bis ${formatContractDate(deadline.toISOString())}`,
      tone: "text-amber-200 bg-amber-300/10 border-amber-300/20",
      icon: FiAlertTriangle,
    };
  }

  return {
    key: "active",
    label: "Aktiv",
    deadline: `Kündbar bis ${formatContractDate(deadline.toISOString())}`,
    tone: "text-[#b8f15a] bg-[#b8f15a]/10 border-[#b8f15a]/15",
    icon: FiCheckCircle,
  };
};
