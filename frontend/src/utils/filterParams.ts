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

const addNumberParam = (
    params: ContractQueryParams,
    key: string,
    value: string
) => {
    if (!value) return

    const parsed = parseGermanNumber(value)
    if (parsed === null) return

    params[key] = parsed
}

export const buildContractQueryParams = (
    filters: ContractFilterState | null | undefined
): ContractQueryParams => {
    const params: ContractQueryParams = {}
    if (!filters) return params

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
