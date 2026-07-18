const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const EXPLICIT_OFFSET_PATTERN = /(?:z|[+-]\d{2}:?\d{2})$/i;

/**
 * SQLite returns timezone-less ISO datetimes even though the application stores
 * UTC. Make that wire convention explicit so parsing never depends on the
 * browser's local timezone.
 */
export const parseApiDate = (value: string): Date => {
  const normalized = DATE_ONLY_PATTERN.test(value)
    ? `${value}T00:00:00Z`
    : EXPLICIT_OFFSET_PATTERN.test(value)
      ? value
      : `${value}Z`;
  return new Date(normalized);
};

export const dateInputToUtcIso = (value: string): string =>
  value ? `${value}T00:00:00.000Z` : "";
