import axios from 'axios'
import { buildContractQueryParams, type ContractFilterState } from './utils/filterParams'

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '/api',
    withCredentials: true, // Required for HttpOnly cookie authentication
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
