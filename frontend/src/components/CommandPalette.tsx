import React, { useEffect, useState } from 'react'
import { Command } from 'cmdk'
import { FiSearch, FiFileText } from 'react-icons/fi'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import type { Contract } from '../types'

const CommandPalette = () => {
    const navigate = useNavigate()
    const [open, setOpen] = useState(false)
    const [contracts, setContracts] = useState<Contract[]>([])

    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((open) => !open)
            }
        }
        document.addEventListener('keydown', down)

        api.get<Contract[]>('/contracts').then(res => setContracts(res.data)).catch(() => setContracts([]))

        return () => document.removeEventListener('keydown', down)
    }, [])

    return (
        <div className="fixed z-50">
            {open && <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setOpen(false)} />}
            <Command.Dialog open={open} onOpenChange={setOpen} label="Global Search" className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-2">
                <div className="flex items-center px-4 border-b border-gray-800">
                    <FiSearch className="text-gray-400 mr-2" />
                    <Command.Input placeholder="Suche Verträge, Tags, Aktionen..." className="w-full bg-transparent py-4 text-white focus:outline-none" />
                </div>
                <Command.List className="py-2 px-2 max-h-96 overflow-y-auto">
                    <Command.Empty className="py-6 text-center text-gray-500">Keine Ergebnisse gefunden.</Command.Empty>

                    <Command.Group heading="Verträge" className="text-gray-500 text-xs font-medium mb-2 px-2">
                        {contracts.map(contract => (
                            <Command.Item
                                key={contract.id}
                                value={`${contract.title} ${contract.description}`}
                                onSelect={() => {
                                    navigate('/contracts')
                                    setOpen(false)
                                }}
                                className="flex items-center px-2 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800 hover:text-white cursor-pointer transition-colors"
                            >
                                <FiFileText className="mr-2" />
                                <span>{contract.title}</span>
                                <span className="ml-auto text-xs opacity-50">
                                    {contract.end_date ? new Date(contract.end_date).toLocaleDateString('de-DE') : 'Unbefristet'}
                                </span>
                            </Command.Item>
                        ))}
                    </Command.Group>

                    <Command.Group heading="Aktionen" className="text-gray-500 text-xs font-medium mb-2 px-2 mt-2">
                        <Command.Item value="toggle-dark" className="flex items-center px-2 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800 hover:text-white cursor-pointer">
                            Theme ändern
                        </Command.Item>
                        <Command.Item value="upload" onSelect={() => setOpen(false)} className="flex items-center px-2 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800 hover:text-white cursor-pointer">
                            Vertrag hochladen
                        </Command.Item>
                    </Command.Group>
                </Command.List>
            </Command.Dialog>
        </div>
    )
}

export default CommandPalette
