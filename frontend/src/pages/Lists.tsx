import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FiPlus, FiFolder, FiEdit2, FiTrash2, FiFileText } from 'react-icons/fi'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import ListModal from '../components/ListModal'
import { useUser } from '../App'

interface ContractList {
    id: number
    name: string
    description: string | null
    color: string
    created_at: string
    contract_count: number
}

const Lists: React.FC = () => {
    const navigate = useNavigate()
    const { isAdmin } = useUser()
    const queryClient = useQueryClient()
    const [isModalOpen, setIsModalOpen] = useState(false)
    const [editingList, setEditingList] = useState<ContractList | null>(null)
    const [isLoading, setIsLoading] = useState(false)

    const { data: lists, isLoading: isLoadingLists } = useQuery<ContractList[]>(['lists'], async () => {
        const res = await api.get('/lists')
        return res.data
    })

    const handleCreateOrEdit = async (data: { name: string; description: string; color: string }) => {
        setIsLoading(true)
        try {
            if (editingList) {
                await api.put(`/lists/${editingList.id}`, data)
            } else {
                await api.post('/lists', data)
            }
            queryClient.invalidateQueries(['lists'])
            setIsModalOpen(false)
            setEditingList(null)
        } catch (e: any) {
            console.error('Failed to save list', e)
            alert(e.response?.data?.detail || 'Fehler beim Speichern der Liste')
        } finally {
            setIsLoading(false)
        }
    }

    const handleDelete = async (list: ContractList) => {
        if (!window.confirm(`Möchten Sie die Liste "${list.name}" wirklich löschen? Die Verträge werden nicht gelöscht.`)) {
            return
        }
        try {
            await api.delete(`/lists/${list.id}`)
            queryClient.invalidateQueries(['lists'])
        } catch (e: any) {
            console.error('Failed to delete list', e)
            alert(e.response?.data?.detail || 'Fehler beim Löschen der Liste')
        }
    }

    const handleViewContracts = (listId: number) => {
        // Navigate to dashboard with list filter
        navigate(`/?list_id=${listId}`)
    }

    if (isLoadingLists) {
        return <div className="p-8 text-center text-gray-400">Lade Listen...</div>
    }

    return (
        <div className="w-full bg-gray-950 p-0 md:p-8">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 p-4 md:p-0">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2">Listen</h1>
                    <p className="text-gray-400">Organisieren Sie Ihre Verträge in benutzerdefinierten Listen.</p>
                </div>
                {isAdmin && (
                    <button
                        onClick={() => {
                            setEditingList(null)
                            setIsModalOpen(true)
                        }}
                        className="mt-4 md:mt-0 w-full md:w-auto flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors shadow-lg shadow-blue-500/20"
                    >
                        <FiPlus />
                        <span>Neue Liste</span>
                    </button>
                )}
            </div>

            {lists && lists.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {lists.map((list) => (
                        <div
                            key={list.id}
                            className="bg-gray-800 border border-gray-700 rounded-xl p-6 hover:border-gray-600 transition-all group relative hover:-translate-y-1 hover:shadow-xl"
                            style={{ borderLeftColor: list.color, borderLeftWidth: '4px' }}
                        >
                            <div className="flex justify-between items-start mb-4">
                                <div
                                    className="p-3 rounded-lg transition-colors"
                                    style={{ backgroundColor: `${list.color}20` }}
                                >
                                    <FiFolder size={24} style={{ color: list.color }} />
                                </div>
                                {isAdmin && (
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => {
                                                setEditingList(list)
                                                setIsModalOpen(true)
                                            }}
                                            className="p-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-xs transition-colors"
                                            title="Bearbeiten"
                                        >
                                            <FiEdit2 size={16} />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(list)}
                                            className="p-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-lg text-xs transition-colors"
                                            title="Löschen"
                                        >
                                            <FiTrash2 size={16} />
                                        </button>
                                    </div>
                                )}
                            </div>

                            <h3 className="text-lg font-semibold text-white mb-1">{list.name}</h3>
                            <p className="text-sm text-gray-400 mb-4 line-clamp-2 h-10">
                                {list.description || 'Keine Beschreibung'}
                            </p>

                            <div className="flex justify-between items-center text-xs text-gray-500 mb-4 border-t border-gray-700/50 pt-4">
                                <div className="flex items-center gap-1">
                                    <FiFileText />
                                    <span>{list.contract_count} Verträge</span>
                                </div>
                                <span>
                                    Erstellt: {new Date(list.created_at).toLocaleDateString('de-DE')}
                                </span>
                            </div>

                            <button
                                onClick={() => handleViewContracts(list.id)}
                                className="w-full flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 text-gray-200 py-2 rounded-lg transition-colors text-sm"
                            >
                                <FiFileText />
                                <span>Verträge anzeigen</span>
                            </button>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="text-center py-16">
                    <div
                        className="w-20 h-20 mx-auto rounded-full flex items-center justify-center mb-4"
                        style={{ backgroundColor: '#6366f120' }}
                    >
                        <FiFolder size={40} className="text-indigo-400" />
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2">Keine Listen vorhanden</h3>
                    <p className="text-gray-400 mb-6">
                        {isAdmin
                            ? 'Erstellen Sie Ihre erste Liste, um Verträge zu organisieren.'
                            : 'Keine Listen mit freigegebenen Verträgen vorhanden.'}
                    </p>
                    {isAdmin && (
                        <button
                            onClick={() => {
                                setEditingList(null)
                                setIsModalOpen(true)
                            }}
                            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-lg font-medium transition-colors"
                        >
                            <FiPlus />
                            <span>Erste Liste erstellen</span>
                        </button>
                    )}
                </div>
            )}

            <ListModal
                isOpen={isModalOpen}
                onClose={() => {
                    setIsModalOpen(false)
                    setEditingList(null)
                }}
                onSubmit={handleCreateOrEdit}
                initialData={editingList}
                isLoading={isLoading}
            />
        </div>
    )
}

export default Lists
