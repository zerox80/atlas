/**
 * Formats a number or numeric string to German format (e.g., 17100 -> "17.100").
 * Thousands separator: dot (.)
 * Decimal separator: comma (,)
 */
export const formatGermanNumber = (value: number | string | null | undefined, includeDecimals = false): string => {
    if (value === null || value === undefined || value === '') return '';

    const num = typeof value === 'string' ? parseGermanNumber(value) : value;

    if (num === null || isNaN(num)) return '';

    return new Intl.NumberFormat('de-DE', {
        minimumFractionDigits: includeDecimals ? 2 : 0,
        maximumFractionDigits: 2,
    }).format(num);
};

/**
 * Parses a German formatted number string back to a float (e.g., "1.234,56" -> 1234.56).
 */
export const parseGermanNumber = (value: string): number | null => {
    const trimmed = value.trim();
    if (!trimmed) return null;

    const compact = trimmed.replace(/\s/g, '');
    const hasCommaDecimal = compact.includes(',');
    const hasGermanThousands = /^\d{1,3}(\.\d{3})+(,\d+)?$/.test(compact);

    const normalized = hasCommaDecimal || hasGermanThousands
        ? compact.replace(/\./g, '').replace(',', '.')
        : compact;

    if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;

    const num = Number(normalized);
    return Number.isFinite(num) ? num : null;
};

/**
 * Formats a number as Euro currency (e.g., 1234.56 -> "1.234,56 €")
 */
export const formatCurrency = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return '0,00 €';

    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
    }).format(value);
};
