import { FiAlertTriangle, FiCheckCircle, FiClock } from "react-icons/fi";
import type { IconType } from "react-icons";
import type { Contract } from "../types";
import { parseApiDate } from "./apiDate";

const DEFAULT_NOTICE_PERIOD = 30;

export type ContractStateKey = "active" | "attention" | "expired";

export interface ContractState {
  key: ContractStateKey;
  label: string;
  deadline: string;
  tone: string;
  icon: IconType;
}

const DAY_MS = 86_400_000;
export const DEFAULT_BUSINESS_TIMEZONE = "Europe/Berlin";
const dayFormatters = new Map<string, Intl.DateTimeFormat>();

const dayFormatter = (timeZone: string): Intl.DateTimeFormat => {
  const cached = dayFormatters.get(timeZone);
  if (cached) return cached;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  dayFormatters.set(timeZone, formatter);
  return formatter;
};

export const businessDateKey = (
  value: string | Date,
  timeZone = DEFAULT_BUSINESS_TIMEZONE,
): string => {
  const date = typeof value === "string" ? parseApiDate(value) : value;
  const values: Record<string, number> = {};
  for (const part of dayFormatter(timeZone).formatToParts(date)) {
    if (part.type === "year" || part.type === "month" || part.type === "day")
      values[part.type] = Number(part.value);
  }
  return `${values.year}-${String(values.month).padStart(2, "0")}-${String(
    values.day,
  ).padStart(2, "0")}`;
};

const calendarDay = (date: Date, timeZone: string): number => {
  const dateKey = businessDateKey(date, timeZone);
  const year = Number(dateKey.slice(0, 4));
  const month = Number(dateKey.slice(5, 7));
  const day = Number(dateKey.slice(8, 10));
  return Date.UTC(year, month - 1, day) / DAY_MS;
};

export const formatContractDate = (
  value?: string | null,
  timeZone?: string,
  options?: Intl.DateTimeFormatOptions,
): string =>
  value
    ? parseApiDate(value).toLocaleDateString(
        "de-DE",
        timeZone || options
          ? { ...options, ...(timeZone ? { timeZone } : {}) }
          : undefined,
      )
    : "Offen";

const dateKeyToCalendarDay = (dateKey: string): number => {
  const year = Number(dateKey.slice(0, 4));
  const month = Number(dateKey.slice(5, 7));
  const day = Number(dateKey.slice(8, 10));
  return Date.UTC(year, month - 1, day) / DAY_MS;
};

const calendarDayToDateKey = (calendarDayValue: number): string =>
  new Date(calendarDayValue * DAY_MS).toISOString().slice(0, 10);

export const formatBusinessDateKey = (dateKey: string): string =>
  new Date(`${dateKey}T00:00:00Z`).toLocaleDateString("de-DE", {
    timeZone: "UTC",
  });

export const getCancellationDeadline = (contract: Contract): string | null => {
  if (!contract.end_date) return null;
  const timeZone = contract.business_timezone || DEFAULT_BUSINESS_TIMEZONE;
  const endDateKey = businessDateKey(contract.end_date, timeZone);
  return calendarDayToDateKey(
    dateKeyToCalendarDay(endDateKey) -
      (contract.notice_period ?? DEFAULT_NOTICE_PERIOD),
  );
};

export const getDaysUntilCancellation = (contract: Contract): number => {
  const deadline = getCancellationDeadline(contract);
  if (!deadline) return Number.POSITIVE_INFINITY;
  const timeZone = contract.business_timezone || DEFAULT_BUSINESS_TIMEZONE;
  return dateKeyToCalendarDay(deadline) - calendarDay(new Date(), timeZone);
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

  const end = parseApiDate(contract.end_date);
  const deadline = getCancellationDeadline(contract)!;
  const timeZone = contract.business_timezone || DEFAULT_BUSINESS_TIMEZONE;
  const today = calendarDay(new Date(), timeZone);
  const endDay = calendarDay(end, timeZone);
  const days = getDaysUntilCancellation(contract);

  if (endDay < today) {
    return {
      key: "expired",
      label: "Abgelaufen",
      deadline: `Endete am ${formatContractDate(contract.end_date, timeZone)}`,
      tone: "text-[#7d8796] bg-white/[0.04] border-white/[0.07]",
      icon: FiClock,
    };
  }

  if (days <= 30) {
    return {
      key: "attention",
      label: days < 0 ? "Frist verpasst" : `${days} Tage`,
      deadline: `Kündbar bis ${formatBusinessDateKey(deadline)}`,
      tone: "text-amber-200 bg-amber-300/10 border-amber-300/20",
      icon: FiAlertTriangle,
    };
  }

  return {
    key: "active",
    label: "Aktiv",
    deadline: `Kündbar bis ${formatBusinessDateKey(deadline)}`,
    tone: "text-[#b8f15a] bg-[#b8f15a]/10 border-[#b8f15a]/15",
    icon: FiCheckCircle,
  };
};
