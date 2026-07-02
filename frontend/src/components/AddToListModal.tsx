import React, { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { FiX, FiCheck, FiFolder } from 'react-icons/fi'
import api from '../api'

interface ContractList {
    id: number
    name: string
    description: string | null
    color: string
    contract_count: number
}

interface AddToListModalProps {
    isOpen: boolean
    onClose: () => void
    contractId: number | null
    contractTitle: string
}

const AddToListModal: React.FC<AddToListModalProps> = ({ isOpen, onClose, contractId, contractTitle }) => {
    const queryClient = useQueryClient()
    const [contractLists, setContractLists] = useState<number[]>([])
    const [isLoading, setIsLoading] = useState(false)

    // Fetch all lists
    const { data: lists } = useQuery<ContractList[]>(['lists'], async () => {
        const res = await api.get('/lists')
        return res.data
    }, { enabled: isOpen })

    // Fetch current contract's lists when modal opens
    useEffect(() => {
        if (isOpen && contractId) {
            // Get current assignments by checking each list
            const fetchContractLists = async () => {
                try {
                    const res = await api.get('/contracts', { params: {} })
                    const contract = res.data.find((c: any) => c.id === contractId)
                    if (contract && contract.lists) {
                        setContractLists(contract.lists.map((l: any) => l.id))
                    } else {
                        setContractLists([])
                    }
                } catch {
                    setContractLists([])
                }
            }
            fetchContractLists()
        }
    }, [isOpen, contractId])

    const handleToggleList = async (listId: number) => {
        if (!contractId) return
        setIsLoading(true)

        try {
            if (contractLists.includes(listId)) {
                // Remove from list
                await api.delete(`/lists/${listId}/contracts/${contractId}`)
                setContractLists(prev => prev.filter(id => id !== listId))
            } else {
                // Add to list
                await api.post(`/lists/${listId}/contracts/${contractId}`)
                setContractLists(prev => [...prev, listId])
            }
            // Invalidate queries to refresh data
            queryClient.invalidateQueries(['lists'])
            queryClient.invalidateQueries(['contracts'])
        } catch (e: any) {
            console.error('Failed to update list assignment', e)
            alert(e.response?.data?.detail || 'Fehler beim Aktualisieren der Listenzuweisung')
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40"
                        onClick={onClose}
                    />
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 20 }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
                    >
                        <div className="bg-gray-900 border border-gray-700 w-full max-w-md rounded-2xl shadow-2xl pointer-events-auto">
                            <div className="flex justify-between items-center p-6 border-b border-gray-800">
                                <div>
                                    <h3 className="text-xl font-semibold text-white">Zu Liste hinzufügen</h3>
                                    <p className="text-sm text-gray-400 mt-1 truncate max-w-[250px]">{contractTitle}</p>
                                </div>
                                <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                                    <FiX size={24} />
                                </button>
                            </div>

                            <div className="p-6 max-h-[400px] overflow-y-auto">
                                {lists && lists.length > 0 ? (
                                    <div className="space-y-2">
                                        {lists.map((list) => {
                                            const isAssigned = contractLists.includes(list.id)
                                            return (
                                                <button
                                                    key={list.id}
                                                    onClick={() => handleToggleList(list.id)}
                                                    disabled={isLoading}
                                                    className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${isAssigned
                                                        ? 'border-green-500/50 bg-green-900/20'
                                                        : 'border-gray-700 hover:border-gray-600 bg-gray-800/50'
                                                        } disabled:opacity-50`}
                                                >
                                                    <div
                                                        className="p-2 rounded-lg flex-shrink-0"
                                                        style={{ backgroundColor: `${list.color}30` }}
                                                    >
                                                        <FiFolder size={18} style={{ color: list.color }} />
                                                    </div>
                                                    <div className="flex-1 text-left">
                                                        <p className="font-medium text-white">{list.name}</p>
                                                        {list.description && (
                                                            <p className="text-sm text-gray-400 truncate">{list.description}</p>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs text-gray-500">{list.contract_count} Verträge</span>
                                                        {isAssigned && (
                                                            <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
                                                                <FiCheck size={14} className="text-white" />
                                                            </div>
                                                        )}
                                                    </div>
                                                </button>
                                            )
                                        })}
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <FiFolder size={48} className="mx-auto text-gray-600 mb-3" />
                                        <p className="text-gray-400">Keine Listen vorhanden</p>
                                        <p className="text-sm text-gray-500 mt-1">Erstellen Sie zuerst eine Liste im Listen-Bereich</p>
                                    </div>
                                )}
                            </div>

                            <div className="p-4 border-t border-gray-800">
                                <button
                                    onClick={onClose}
                                    className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 rounded-lg transition-colors"
                                >
                                    Schließen
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    )
}

export default AddToListModal
