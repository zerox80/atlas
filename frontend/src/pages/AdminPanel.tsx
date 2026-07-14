import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FiUsers, FiPlus, FiEdit2, FiTrash2, FiShield, FiCheck, FiX, FiLock, FiTag } from 'react-icons/fi'
import api from '../api'
import { LoadingState, PageHeader } from '../components/ui'

interface User {
    id: number
    username: string
    role: string
    is_active: boolean
    created_at: string
    has_2fa: boolean
}

interface Contract {
    id: number
    title: string
}

interface Permission {
    id: number
    user_id: number
    contract_id: number
    permission_level: string
    username: string
    contract_title: string
}

interface Tag {
    id: number
    name: string
    color: string
}

const AdminPanel: React.FC = () => {
    const [users, setUsers] = useState<User[]>([])
    const [contracts, setContracts] = useState<Contract[]>([])
    const [permissions, setPermissions] = useState<Permission[]>([])
    const [tags, setTags] = useState<Tag[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [activeTab, setActiveTab] = useState<'users' | 'permissions' | 'tags'>('users')

    // Modal states
    const [isAddUserModalOpen, setIsAddUserModalOpen] = useState(false)
    const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false)
    const [isPermissionModalOpen, setIsPermissionModalOpen] = useState(false)
    const [selectedUser, setSelectedUser] = useState<User | null>(null)

    // Form states
    const [newUsername, setNewUsername] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [editRole, setEditRole] = useState('user')
    const [editIsActive, setEditIsActive] = useState(true)

    // Permission form
    const [permUserId, setPermUserId] = useState<number>(0)
    const [permContractId, setPermContractId] = useState<number>(0)
    const [permLevel, setPermLevel] = useState<string>('read')

    // Tag states
    const [isAddTagModalOpen, setIsAddTagModalOpen] = useState(false)
    const [isEditTagModalOpen, setIsEditTagModalOpen] = useState(false)
    const [selectedTag, setSelectedTag] = useState<Tag | null>(null)
    const [newTagName, setNewTagName] = useState('')
    const [newTagColor, setNewTagColor] = useState('#3b82f6')
    const [editTagName, setEditTagName] = useState('')
    const [editTagColor, setEditTagColor] = useState('#3b82f6')

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        setIsLoading(true)
        try {
            const [usersRes, contractsRes, permsRes, tagsRes] = await Promise.all([
                api.get('/admin/users'),
                api.get('/contracts'),
                api.get('/admin/permissions'),
                api.get('/tags')
            ])
            setUsers(usersRes.data)
            setContracts(contractsRes.data)
            setPermissions(permsRes.data)
            setTags(tagsRes.data)
        } catch (error) {
            console.error('Failed to load admin data:', error)
        } finally {
            setIsLoading(false)
        }
    }

    const handleAddUser = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            await api.post('/admin/users', {
                username: newUsername,
                password: newPassword
            })
            setNewUsername('')
            setNewPassword('')
            setIsAddUserModalOpen(false)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Erstellen')
        }
    }

    const handleUpdateUser = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!selectedUser) return
        try {
            await api.put(`/admin/users/${selectedUser.id}`, {
                role: editRole,
                is_active: editIsActive
            })
            setIsEditUserModalOpen(false)
            setSelectedUser(null)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Aktualisieren')
        }
    }

    const handleDeleteUser = async (userId: number) => {
        if (!confirm('Benutzer wirklich deaktivieren?')) return
        try {
            await api.delete(`/admin/users/${userId}`)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Deaktivieren')
        }
    }

    const handleAddPermission = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            await api.post('/admin/permissions', {
                user_id: permUserId,
                contract_id: permContractId,
                permission_level: permLevel
            })
            setIsPermissionModalOpen(false)
            setPermUserId(0)
            setPermContractId(0)
            setPermLevel('read')
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Erstellen')
        }
    }

    const handleDeletePermission = async (permId: number) => {
        if (!confirm('Berechtigung wirklich entfernen?')) return
        try {
            await api.delete(`/admin/permissions/${permId}`)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Löschen')
        }
    }

    const openEditUser = (user: User) => {
        setSelectedUser(user)
        setEditRole(user.role)
        setEditIsActive(user.is_active)
        setIsEditUserModalOpen(true)
    }

    const getLevelColor = (level: string) => {
        switch (level) {
            case 'full': return 'text-red-400 bg-red-500/20'
            case 'write': return 'text-yellow-400 bg-yellow-500/20'
            case 'read': return 'text-green-400 bg-green-500/20'
            default: return 'text-gray-400 bg-gray-500/20'
        }
    }

    const getLevelLabel = (level: string) => {
        switch (level) {
            case 'full': return 'Vollzugriff'
            case 'write': return 'Bearbeiten'
            case 'read': return 'Nur Lesen'
            default: return level
        }
    }

    // Tag handlers
    const handleAddTag = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            await api.post('/tags', {
                name: newTagName,
                color: newTagColor
            })
            setNewTagName('')
            setNewTagColor('#3b82f6')
            setIsAddTagModalOpen(false)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Erstellen')
        }
    }

    const handleUpdateTag = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!selectedTag) return
        try {
            await api.put(`/tags/${selectedTag.id}`, {
                name: editTagName,
                color: editTagColor
            })
            setIsEditTagModalOpen(false)
            setSelectedTag(null)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Aktualisieren')
        }
    }

    const handleDeleteTag = async (tagId: number) => {
        if (!confirm('Tag wirklich löschen? Er wird von allen Verträgen entfernt.')) return
        try {
            await api.delete(`/tags/${tagId}`)
            loadData()
        } catch (error: any) {
            alert(error.response?.data?.detail || 'Fehler beim Löschen')
        }
    }

    const openEditTag = (tag: Tag) => {
        setSelectedTag(tag)
        setEditTagName(tag.name)
        setEditTagColor(tag.color)
        setIsEditTagModalOpen(true)
    }

    if (isLoading) {
        return <LoadingState label="Administration wird geladen" />
    }

    return (
        <div className="app-page">
            <PageHeader eyebrow="System / Control Center" title="Administration" description="Benutzer, Dokumentrechte und Taxonomie an einem zentralen Kontrollpunkt verwalten." actions={<span className="chip border-[#b8f15a]/20 bg-[#b8f15a]/[0.07] text-[#b8f15a]"><FiShield /> Admin access</span>} />

            <div className="mb-5 grid gap-3 sm:grid-cols-3">
                <div className="surface p-5"><p className="eyebrow">Benutzer</p><p className="metric-value mt-3">{users.length}</p><p className="mt-2 text-xs text-white/34">{users.filter((user) => user.is_active).length} aktiv</p></div>
                <div className="surface p-5"><p className="eyebrow">Freigaben</p><p className="metric-value mt-3">{permissions.length}</p><p className="mt-2 text-xs text-white/34">Dokumentbezogene Rechte</p></div>
                <div className="surface p-5"><p className="eyebrow">Taxonomie</p><p className="metric-value mt-3">{tags.length}</p><p className="mt-2 text-xs text-white/34">Verfügbare Tags</p></div>
            </div>

            {/* Tabs */}
            <div className="surface mb-6 flex flex-wrap gap-1 p-1.5">
                <button
                    onClick={() => setActiveTab('users')}
                    className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'users'
                        ? 'bg-white/[0.09] text-white'
                        : 'text-white/38 hover:bg-white/[0.04] hover:text-white'
                        }`}
                >
                    <FiUsers />
                    Benutzer ({users.length})
                </button>
                <button
                    onClick={() => setActiveTab('permissions')}
                    className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'permissions'
                        ? 'bg-white/[0.09] text-white'
                        : 'text-white/38 hover:bg-white/[0.04] hover:text-white'
                        }`}
                >
                    <FiLock />
                    Berechtigungen ({permissions.length})
                </button>
                <button
                    onClick={() => setActiveTab('tags')}
                    className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'tags'
                        ? 'bg-white/[0.09] text-white'
                        : 'text-white/38 hover:bg-white/[0.04] hover:text-white'
                        }`}
                >
                    <FiTag />
                    Tags ({tags.length})
                </button>
            </div>

            {/* Users Tab */}
            {activeTab === 'users' && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-4"
                >
                    <div className="flex justify-end">
                        <button
                            onClick={() => setIsAddUserModalOpen(true)}
                            className="btn-primary"
                        >
                            <FiPlus /> Neuer Benutzer
                        </button>
                    </div>

                    <div className="surface overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-gray-900/50">
                                <tr>
                                    <th className="text-left p-4 text-gray-400 font-medium">Benutzer</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Rolle</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Status</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">2FA</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Aktionen</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((user) => (
                                    <tr key={user.id} className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors">
                                        <td className="p-4">
                                            <span className="text-white font-medium">{user.username}</span>
                                        </td>
                                        <td className="p-4">
                                            <span className={`px-2 py-1 rounded text-sm ${user.role === 'admin'
                                                ? 'bg-purple-500/20 text-purple-400'
                                                : 'bg-gray-500/20 text-gray-400'
                                                }`}>
                                                {user.role === 'admin' ? 'Admin' : 'Benutzer'}
                                            </span>
                                        </td>
                                        <td className="p-4">
                                            {user.is_active ? (
                                                <span className="flex items-center gap-1 text-green-400">
                                                    <FiCheck /> Aktiv
                                                </span>
                                            ) : (
                                                <span className="flex items-center gap-1 text-red-400">
                                                    <FiX /> Inaktiv
                                                </span>
                                            )}
                                        </td>
                                        <td className="p-4">
                                            {user.has_2fa ? (
                                                <span className="text-green-400"><FiShield /></span>
                                            ) : (
                                                <span className="text-gray-500">—</span>
                                            )}
                                        </td>
                                        <td className="p-4 text-right space-x-2">
                                            <button
                                                onClick={() => openEditUser(user)}
                                                className="p-2 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                                                title="Bearbeiten"
                                            >
                                                <FiEdit2 />
                                            </button>
                                            <button
                                                onClick={() => handleDeleteUser(user.id)}
                                                className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                                                title="Deaktivieren"
                                            >
                                                <FiTrash2 />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </motion.div>
            )}

            {/* Permissions Tab */}
            {activeTab === 'permissions' && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-4"
                >
                    <div className="flex justify-end">
                        <button
                            onClick={() => setIsPermissionModalOpen(true)}
                            className="btn-primary"
                        >
                            <FiPlus /> Berechtigung hinzufügen
                        </button>
                    </div>

                    <div className="surface overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-gray-900/50">
                                <tr>
                                    <th className="text-left p-4 text-gray-400 font-medium">Benutzer</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Vertrag</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Berechtigung</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Aktionen</th>
                                </tr>
                            </thead>
                            <tbody>
                                {permissions.length === 0 ? (
                                    <tr>
                                        <td colSpan={4} className="p-8 text-center text-gray-500">
                                            Keine Berechtigungen vorhanden
                                        </td>
                                    </tr>
                                ) : (
                                    permissions.map((perm) => (
                                        <tr key={perm.id} className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors">
                                            <td className="p-4 text-white">{perm.username}</td>
                                            <td className="p-4 text-gray-300">{perm.contract_title}</td>
                                            <td className="p-4">
                                                <span className={`px-2 py-1 rounded text-sm ${getLevelColor(perm.permission_level)}`}>
                                                    {getLevelLabel(perm.permission_level)}
                                                </span>
                                            </td>
                                            <td className="p-4 text-right">
                                                <button
                                                    onClick={() => handleDeletePermission(perm.id)}
                                                    className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                                                    title="Entfernen"
                                                >
                                                    <FiTrash2 />
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </motion.div>
            )}

            {/* Tags Tab */}
            {activeTab === 'tags' && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-4"
                >
                    <div className="flex justify-end">
                        <button
                            onClick={() => setIsAddTagModalOpen(true)}
                            className="btn-primary"
                        >
                            <FiPlus /> Neuer Tag
                        </button>
                    </div>

                    <div className="surface overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-gray-900/50">
                                <tr>
                                    <th className="text-left p-4 text-gray-400 font-medium">Farbe</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Name</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Aktionen</th>
                                </tr>
                            </thead>
                            <tbody>
                                {tags.length === 0 ? (
                                    <tr>
                                        <td colSpan={3} className="p-8 text-center text-gray-500">
                                            Keine Tags vorhanden
                                        </td>
                                    </tr>
                                ) : (
                                    tags.map((tag) => (
                                        <tr key={tag.id} className="border-t border-gray-700 hover:bg-gray-800/50 transition-colors">
                                            <td className="p-4">
                                                <div
                                                    className="w-8 h-8 rounded-lg border-2 border-gray-600"
                                                    style={{ backgroundColor: tag.color }}
                                                />
                                            </td>
                                            <td className="p-4">
                                                <span
                                                    className="px-3 py-1 rounded-full text-sm font-medium"
                                                    style={{
                                                        backgroundColor: `${tag.color}20`,
                                                        color: tag.color
                                                    }}
                                                >
                                                    {tag.name}
                                                </span>
                                            </td>
                                            <td className="p-4 text-right space-x-2">
                                                <button
                                                    onClick={() => openEditTag(tag)}
                                                    className="p-2 text-blue-400 hover:bg-blue-500/20 rounded transition-colors"
                                                    title="Bearbeiten"
                                                >
                                                    <FiEdit2 />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteTag(tag.id)}
                                                    className="p-2 text-red-400 hover:bg-red-500/20 rounded transition-colors"
                                                    title="Löschen"
                                                >
                                                    <FiTrash2 />
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </motion.div>
            )}

            {/* Add User Modal */}
            <AnimatePresence>
                {isAddUserModalOpen && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
                        onClick={() => setIsAddUserModalOpen(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h2 className="text-xl font-bold text-white mb-4">Neuer Benutzer</h2>
                            <form onSubmit={handleAddUser} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Benutzername</label>
                                    <input
                                        type="text"
                                        value={newUsername}
                                        onChange={(e) => setNewUsername(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        required
                                        minLength={3}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Passwort</label>
                                    <input
                                        type="password"
                                        value={newPassword}
                                        onChange={(e) => setNewPassword(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        required
                                        minLength={8}
                                    />
                                </div>
                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsAddUserModalOpen(false)}
                                        className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                                    >
                                        Abbrechen
                                    </button>
                                    <button
                                        type="submit"
                                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                                    >
                                        Erstellen
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Edit User Modal */}
            <AnimatePresence>
                {isEditUserModalOpen && selectedUser && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
                        onClick={() => setIsEditUserModalOpen(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h2 className="text-xl font-bold text-white mb-4">Benutzer bearbeiten: {selectedUser.username}</h2>
                            <form onSubmit={handleUpdateUser} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Rolle</label>
                                    <select
                                        value={editRole}
                                        onChange={(e) => setEditRole(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                    >
                                        <option value="user">Benutzer</option>
                                        <option value="admin">Admin</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="flex items-center gap-3 text-gray-400 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={editIsActive}
                                            onChange={(e) => setEditIsActive(e.target.checked)}
                                            className="w-5 h-5 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
                                        />
                                        Benutzer ist aktiv
                                    </label>
                                </div>
                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsEditUserModalOpen(false)}
                                        className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                                    >
                                        Abbrechen
                                    </button>
                                    <button
                                        type="submit"
                                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                                    >
                                        Speichern
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Add Permission Modal */}
            <AnimatePresence>
                {isPermissionModalOpen && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
                        onClick={() => setIsPermissionModalOpen(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h2 className="text-xl font-bold text-white mb-4">Berechtigung hinzufügen</h2>
                            <form onSubmit={handleAddPermission} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Benutzer</label>
                                    <select
                                        value={permUserId}
                                        onChange={(e) => setPermUserId(Number(e.target.value))}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        required
                                    >
                                        <option value={0}>Benutzer wählen...</option>
                                        {users.filter(u => u.role !== 'admin' && u.is_active).map((user) => (
                                            <option key={user.id} value={user.id}>{user.username}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Vertrag</label>
                                    <select
                                        value={permContractId}
                                        onChange={(e) => setPermContractId(Number(e.target.value))}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        required
                                    >
                                        <option value={0}>Vertrag wählen...</option>
                                        {contracts.map((contract) => (
                                            <option key={contract.id} value={contract.id}>{contract.title}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Berechtigung</label>
                                    <select
                                        value={permLevel}
                                        onChange={(e) => setPermLevel(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                    >
                                        <option value="read">Nur Lesen</option>
                                        <option value="write">Bearbeiten</option>
                                        <option value="full">Vollzugriff (inkl. Löschen)</option>
                                    </select>
                                </div>
                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsPermissionModalOpen(false)}
                                        className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                                    >
                                        Abbrechen
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={permUserId === 0 || permContractId === 0}
                                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                                    >
                                        Hinzufügen
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Add Tag Modal */}
            <AnimatePresence>
                {isAddTagModalOpen && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
                        onClick={() => setIsAddTagModalOpen(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h2 className="text-xl font-bold text-white mb-4">Neuer Tag</h2>
                            <form onSubmit={handleAddTag} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Name</label>
                                    <input
                                        type="text"
                                        value={newTagName}
                                        onChange={(e) => setNewTagName(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        placeholder="z.B. Software, Legal, HR..."
                                        required
                                        minLength={1}
                                        maxLength={50}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Farbe</label>
                                    <div className="flex gap-3 items-center">
                                        <input
                                            type="color"
                                            value={newTagColor}
                                            onChange={(e) => setNewTagColor(e.target.value)}
                                            className="w-12 h-12 rounded-lg border-2 border-gray-700 cursor-pointer bg-transparent"
                                        />
                                        <span
                                            className="px-3 py-1 rounded-full text-sm font-medium"
                                            style={{
                                                backgroundColor: `${newTagColor}20`,
                                                color: newTagColor
                                            }}
                                        >
                                            {newTagName || 'Vorschau'}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsAddTagModalOpen(false)}
                                        className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                                    >
                                        Abbrechen
                                    </button>
                                    <button
                                        type="submit"
                                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                                    >
                                        Erstellen
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Edit Tag Modal */}
            <AnimatePresence>
                {isEditTagModalOpen && selectedTag && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
                        onClick={() => setIsEditTagModalOpen(false)}
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h2 className="text-xl font-bold text-white mb-4">Tag bearbeiten</h2>
                            <form onSubmit={handleUpdateTag} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Name</label>
                                    <input
                                        type="text"
                                        value={editTagName}
                                        onChange={(e) => setEditTagName(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                                        required
                                        minLength={1}
                                        maxLength={50}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Farbe</label>
                                    <div className="flex gap-3 items-center">
                                        <input
                                            type="color"
                                            value={editTagColor}
                                            onChange={(e) => setEditTagColor(e.target.value)}
                                            className="w-12 h-12 rounded-lg border-2 border-gray-700 cursor-pointer bg-transparent"
                                        />
                                        <span
                                            className="px-3 py-1 rounded-full text-sm font-medium"
                                            style={{
                                                backgroundColor: `${editTagColor}20`,
                                                color: editTagColor
                                            }}
                                        >
                                            {editTagName || 'Vorschau'}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsEditTagModalOpen(false)}
                                        className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                                    >
                                        Abbrechen
                                    </button>
                                    <button
                                        type="submit"
                                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                                    >
                                        Speichern
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}

export default AdminPanel
