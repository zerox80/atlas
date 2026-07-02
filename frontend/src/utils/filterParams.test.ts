import { describe, expect, it } from 'vitest'
import { buildContractQueryParams } from './filterParams'
import { formatGermanNumber, parseGermanNumber } from './formatUtils'

describe('formatUtils', () => {
    it('parses German number input without silently coercing invalid values', () => {
        expect(parseGermanNumber('17.100,50')).toBe(17100.5)
        expect(parseGermanNumber('17100.50')).toBe(17100.5)
        expect(parseGermanNumber('not a number')).toBeNull()
        expect(parseGermanNumber('')).toBeNull()
    })

    it('formats German number strings correctly', () => {
        expect(formatGermanNumber('17.100,50', true)).toBe('17.100,50')
    })
})

describe('buildContractQueryParams', () => {
    it('serializes UI filters to backend query parameter names', () => {
        expect(buildContractQueryParams({
            q: 'acme',
            tags: ['Software', 'Legal'],
            listId: 12,
            minValue: '1.000,50',
            maxValue: '2.000',
            startDateFrom: '2026-01-01',
            startDateTo: '2026-12-31',
            status: 'active',
            sortBy: 'value',
            sortOrder: 'asc',
        })).toEqual({
            q: 'acme',
            tags: 'Software,Legal',
            list_id: 12,
            min_value: 1000.5,
            max_value: 2000,
            start_date_from: '2026-01-01',
            start_date_to: '2026-12-31',
            status: 'active',
            sort_by: 'value',
            sort_order: 'asc',
        })
    })
})
