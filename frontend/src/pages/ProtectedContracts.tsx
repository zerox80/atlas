
import React, { useState, useEffect } from 'react'
import api, { toggleContractProtection } from '../api'
import { FiShield, FiUnlock, FiTrash2, FiAlertCircle } from 'react-icons/fi'
import { useNavigate } from 'react-router-dom'

interface Contract {
    id: number
    title: string
    description?: string
    start_date: string
    end_date: string
    value: number
    file_extension: string
    is_protected: boolean
}

const ProtectedContracts: React.FC = () => {
    const [contracts, setContracts] = useState<Contract[]>([])
    const [isLoading, setIsLoading] = useState<boolean>(true)
    const [error, setError] = useState<string | null>(null)
    const navigate = useNavigate()

    const fetchProtectedContracts = async () => {
        setIsLoading(true)
        try {
            const response = await api.get<Contract[]>('/contracts')
            // Filter client-side for now as we didn't implement a specific 'protected=true' filter in backend
            // or we can just filter all contracts. 
            // Optimally backend should filter, but client side is fine for reasonable amounts.
            const protectedOnly = response.data.filter(c => c.is_protected)
            setContracts(protectedOnly)
            setError(null)
        } catch (err) {
            console.error('Failed to fetch contracts', err)
            setError('Konnte geschützte Verträge nicht laden.')
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        fetchProtectedContracts()
    }, [])

    const handleUnprotect = async (id: number, title: string) => {
        if (!window.confirm(`Möchten Sie den Schutz für "${title}" wirklich aufheben?`)) {
            return
        }

        try {
            await toggleContractProtection(id)
            // Refresh list
            fetchProtectedContracts()
        } catch (err) {
            console.error('Failed to toggle protection', err)
            alert('Fehler beim Ändern des Status.')
        }
    }

    if (isLoading) {
        return <div className="text-white p-8">Lade geschützte Verträge...</div>
    }

    return (
        <div className="p-6 max-w-7xl mx-auto text-white">
            <h1 className="text-3xl font-bold mb-6 flex items-center gap-3">
                <FiShield className="text-green-500" />
                Geschützte Verträge
            </h1>

            <div className="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700 mb-8">
                <div className="flex items-start gap-3 text-gray-300">
                    <FiAlertCircle className="mt-1 text-blue-400 flex-shrink-0" size={20} />
                    <p>
                        Diese Verträge sind vor dem Löschen geschützt. Selbst Administratoren können diese Verträge nicht direkt löschen.
                        Um einen Vertrag zu löschen, müssen Sie hier zuerst den Schutz aufheben.
                    </p>
                </div>
            </div>

            {error && (
                <div className="bg-red-900/50 border border-red-700 text-red-200 p-4 rounded-lg mb-6">
                    {error}
                </div>
            )}

            {contracts.length === 0 ? (
                <div className="text-center py-12 bg-gray-800 rounded-lg border border-gray-700 border-dashed">
                    <FiShield className="mx-auto h-12 w-12 text-gray-600 mb-3" />
                    <h3 className="text-lg font-medium text-gray-400">Keine geschützten Verträge</h3>
                    <p className="text-gray-500 mt-1">Sie können Verträge im Dashboard schützen.</p>
                    <button
                        onClick={() => navigate('/')}
                        className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                    >
                        Zum Dashboard
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {contracts.map(contract => (
                        <div key={contract.id} className="bg-gray-800 rounded-lg border border-green-900/50 shadow-lg overflow-hidden relative group hover:border-green-500/50 transition-colors">
                            <div className="absolute top-0 right-0 p-2 bg-green-900/80 text-green-200 text-xs font-bold rounded-bl-lg">
                                GESCHÜTZT
                            </div>

                            <div className="p-5">
                                <h3 className="font-bold text-lg mb-2 truncate" title={contract.title}>{contract.title}</h3>
                                <p className="text-sm text-gray-400 mb-4 line-clamp-2">{contract.description || "Keine Beschreibung"}</p>

                                <div className="space-y-2 text-sm text-gray-300 mb-6">
                                    <div className="flex justify-between">
                                        <span>Wert:</span>
                                        <span className="font-mono">{contract.value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>Ende:</span>
                                        <span>{new Date(contract.end_date).toLocaleDateString('de-DE')}</span>
                                    </div>
                                </div>

                                <button
                                    onClick={() => handleUnprotect(contract.id, contract.title)}
                                    className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-gray-700 hover:bg-red-900/50 text-gray-300 hover:text-red-300 rounded transition-all border border-gray-600 hover:border-red-800"
                                >
                                    <FiUnlock />
                                    <span>Schutz aufheben</span>
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

export default ProtectedContracts
