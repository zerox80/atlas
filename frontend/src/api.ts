import axios from 'axios'
import { buildContractQueryParams, type ContractFilterState } from './utils/filterParams'

export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export const buildApiUrl = (path: string) => {
    const normalizedBase = API_BASE_URL.replace(/\/$/, '')
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    return `${normalizedBase}${normalizedPath}`
}

const api = axios.create({
    baseURL: API_BASE_URL,
    withCredentials: true, // Required for HttpOnly cookie authentication
})

export const getCookieValue = (name: string) => {
    const match = document.cookie
        .split('; ')
        .find(row => row.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null
}

const isMutatingMethod = (method?: string) => {
    return ['post', 'put', 'patch', 'delete'].includes((method || 'get').toLowerCase())
}

export const ensureCsrfToken = async () => {
    const existingToken = getCookieValue('csrf_token')
    if (existingToken) return existingToken

    await api.get('/csrf-token')
    return getCookieValue('csrf_token')
}

api.interceptors.request.use(async (config) => {
    if (isMutatingMethod(config.method) && config.url !== '/token') {
        const csrfToken = await ensureCsrfToken()
        if (csrfToken) {
            config.headers = config.headers || {}
            config.headers['X-CSRF-Token'] = csrfToken
        }
    }
    return config
})

api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response && error.response.status === 401) {
            // Check if we are not already on the login page to avoid loops
            if (window.location.pathname !== '/login') {
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
)


export const toggleContractProtection = async (id: number) => {
    return api.put(`/contracts/${id}/toggle-protection`)
}

export const exportContracts = async (filters: ContractFilterState, format: 'csv' | 'excel') => {
    return api.get('/contracts/export', {
        params: { ...buildContractQueryParams(filters), format },
        responseType: 'blob'
    })
}

export default api
