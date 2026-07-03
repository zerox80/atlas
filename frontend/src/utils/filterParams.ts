import { parseGermanNumber } from './formatUtils'

export interface ContractFilterState {
    q: string
    tags: string[]
    listId: number | null
    minValue: string
    maxValue: string
    startDateFrom: string
    startDateTo: string
    status: string
    sortBy: string
    sortOrder: 'asc' | 'desc'
}

export type ContractQueryParams = Record<string, string | number>

export const getContractFilterValidationError = (
    filters: ContractFilterState | null | undefined
) => {
    if (!filters) return null

    if (filters.minValue && parseGermanNumber(filters.minValue) === null) {
        return 'Bitte geben Sie einen gültigen Mindestwert ein.'
    }

    if (filters.maxValue && parseGermanNumber(filters.maxValue) === null) {
        return 'Bitte geben Sie einen gültigen Höchstwert ein.'
    }

    const minValue = filters.minValue ? parseGermanNumber(filters.minValue) : null
    const maxValue = filters.maxValue ? parseGermanNumber(filters.maxValue) : null
    if (minValue !== null && maxValue !== null && minValue > maxValue) {
        return 'Der Mindestwert darf nicht größer als der Höchstwert sein.'
    }

    return null
}

const addNumberParam = (
    params: ContractQueryParams,
    key: string,
    value: string
) => {
    if (!value) return

    const parsed = parseGermanNumber(value)
    if (parsed === null) {
        throw new Error(`Invalid number for ${key}`)
    }

    params[key] = parsed
}

export const buildContractQueryParams = (
    filters: ContractFilterState | null | undefined
): ContractQueryParams => {
    const params: ContractQueryParams = {}
    if (!filters) return params

    const validationError = getContractFilterValidationError(filters)
    if (validationError) {
        throw new Error(validationError)
    }

    if (filters.q) params.q = filters.q
    if (filters.tags.length > 0) params.tags = filters.tags.join(',')
    if (filters.listId !== null) params.list_id = filters.listId
    addNumberParam(params, 'min_value', filters.minValue)
    addNumberParam(params, 'max_value', filters.maxValue)
    if (filters.startDateFrom) params.start_date_from = filters.startDateFrom
    if (filters.startDateTo) params.start_date_to = filters.startDateTo
    if (filters.status) params.status = filters.status
    if (filters.sortBy) params.sort_by = filters.sortBy
    if (filters.sortOrder) params.sort_order = filters.sortOrder

    return params
}
