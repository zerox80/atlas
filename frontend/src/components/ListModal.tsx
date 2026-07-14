import React, { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { FiFolder, FiX } from 'react-icons/fi'

interface ListModalProps {
    isOpen: boolean
    onClose: () => void
    onSubmit: (data: { name: string; description: string; color: string }) => void
    initialData?: { id?: number; name: string; description?: string | null; color: string } | null
    isLoading?: boolean
}

const PRESET_COLORS = ['#b8f15a', '#7397ff', '#9a7cff', '#2dd4bf', '#fbbf24', '#fb7185', '#f472b6', '#38bdf8']

const ListModal: React.FC<ListModalProps> = ({ isOpen, onClose, onSubmit, initialData, isLoading }) => {
    const [name, setName] = useState('')
    const [description, setDescription] = useState('')
    const [color, setColor] = useState('#7397ff')

    useEffect(() => {
        if (!isOpen) return
        setName(initialData?.name || '')
        setDescription(initialData?.description || '')
        setColor(initialData?.color || '#7397ff')
    }, [isOpen, initialData])

    const handleSubmit = (event: React.FormEvent) => {
        event.preventDefault()
        if (name.trim()) onSubmit({ name: name.trim(), description: description.trim(), color })
    }

    return <AnimatePresence>
        {isOpen && <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="fixed inset-0 z-[80] bg-black/75 backdrop-blur-md" />
            <motion.div initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.97 }} className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center p-4">
                <div className="pointer-events-auto w-full max-w-lg overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#0c0f0d] shadow-[0_32px_100px_rgba(0,0,0,.65)]">
                    <header className="flex items-center justify-between border-b border-white/[0.07] p-6">
                        <div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-2xl" style={{ color, backgroundColor: `${color}14`, border: `1px solid ${color}28` }}><FiFolder /></div><div><p className="eyebrow">Collection builder</p><h2 className="mt-1 text-lg font-semibold">{initialData ? 'Sammlung bearbeiten' : 'Neue Sammlung'}</h2></div></div>
                        <button onClick={onClose} className="icon-btn"><FiX /></button>
                    </header>
                    <form onSubmit={handleSubmit} className="space-y-5 p-6">
                        <label className="block"><span className="eyebrow mb-2 block">Name</span><input className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="z. B. Software & Lizenzen" autoFocus required /></label>
                        <label className="block"><span className="eyebrow mb-2 block">Beschreibung</span><textarea className="field min-h-24 resize-none" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Wofür wird diese Sammlung genutzt?" /></label>
                        <div><span className="eyebrow mb-3 block">Akzentfarbe</span><div className="flex flex-wrap gap-2">
                            {PRESET_COLORS.map((preset) => <button key={preset} type="button" onClick={() => setColor(preset)} aria-label={`Farbe ${preset}`} className={`h-9 w-9 rounded-xl transition-transform hover:scale-105 ${color === preset ? 'ring-2 ring-white ring-offset-2 ring-offset-[#0c0f0d]' : ''}`} style={{ backgroundColor: preset }} />)}
                            <input type="color" value={color} onChange={(event) => setColor(event.target.value)} className="h-9 w-9 cursor-pointer rounded-xl border border-dashed border-white/20 bg-transparent p-0.5" title="Eigene Farbe wählen" />
                        </div></div>
                        <div className="rounded-2xl border p-4" style={{ borderColor: `${color}30`, backgroundColor: `${color}08` }}><p className="eyebrow">Live preview</p><div className="mt-3 flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ backgroundColor: `${color}18`, color }}><FiFolder /></div><div className="min-w-0"><p className="truncate text-sm font-semibold">{name || 'Sammlungsname'}</p><p className="mt-1 truncate text-xs text-white/34">{description || 'Deine Beschreibung erscheint hier.'}</p></div></div></div>
                        <div className="flex justify-end gap-2 border-t border-white/[0.07] pt-5"><button type="button" onClick={onClose} className="btn-ghost">Abbrechen</button><button type="submit" disabled={isLoading || !name.trim()} className="btn-primary">{isLoading ? 'Speichern …' : initialData ? 'Änderungen speichern' : 'Sammlung erstellen'}</button></div>
                    </form>
                </div>
            </motion.div>
        </>}
    </AnimatePresence>
}

export default ListModal
