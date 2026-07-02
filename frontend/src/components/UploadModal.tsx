import React, { useCallback, useState, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { FiUploadCloud, FiX, FiZap } from 'react-icons/fi'
import api from '../api'
import { useQueryClient } from '@tanstack/react-query'
import { formatGermanNumber, parseGermanNumber } from '../utils/formatUtils'

interface UploadModalProps {
    isOpen: boolean
    onClose: () => void
    initialData?: any
}

const UploadModal: React.FC<UploadModalProps> = ({ isOpen, onClose, initialData }) => {
    const [file, setFile] = useState<File | null>(null)
    const [title, setTitle] = useState('')
    const [description, setDescription] = useState('')
    const [value, setValue] = useState('')
    const [annualValue, setAnnualValue] = useState('')
    const [tags, setTags] = useState('')
    const [startDate, setStartDate] = useState('')
    const [endDate, setEndDate] = useState('')
    const [noticePeriod, setNoticePeriod] = useState('')
    const [uploading, setUploading] = useState(false)
    const [analyzing, setAnalyzing] = useState(false)

    const queryClient = useQueryClient()

    useEffect(() => {
        if (isOpen && initialData) {
            setTitle(initialData.title || '')
            setDescription(initialData.description || '')
            setValue(initialData.value != null ? formatGermanNumber(initialData.value) : '')
            setAnnualValue(initialData.annual_value != null ? formatGermanNumber(initialData.annual_value) : '')
            setTags(initialData.tags?.map((t: any) => t.name).join(', ') || '')
            setNoticePeriod(initialData.notice_period?.toString() || '30')
            // Format dates for input type="date" (YYYY-MM-DD) - Use local time to avoid timezone shifts
            if (initialData.start_date) {
                const d = new Date(initialData.start_date)
                if (!isNaN(d.getTime())) {
                    const year = d.getFullYear()
                    const month = String(d.getMonth() + 1).padStart(2, '0')
                    const day = String(d.getDate()).padStart(2, '0')
                    setStartDate(`${year}-${month}-${day}`)
                }
            } else {
                setStartDate('')
            }
            if (initialData.end_date) {
                const d = new Date(initialData.end_date)
                if (!isNaN(d.getTime())) {
                    const year = d.getFullYear()
                    const month = String(d.getMonth() + 1).padStart(2, '0')
                    const day = String(d.getDate()).padStart(2, '0')
                    setEndDate(`${year}-${month}-${day}`)
                }
            } else {
                setEndDate('')
            }
            setFile(null)
        } else if (isOpen && !initialData) {
            // Reset for new upload
            setTitle('')
            setDescription('')
            setValue('')
            setAnnualValue('')
            setTags('')
            setNoticePeriod('')
            setStartDate('')
            setEndDate('')
            setFile(null)
        }
    }, [isOpen, initialData])

    const onDrop = useCallback((acceptedFiles: File[]) => {
        if (acceptedFiles.length > 0) {
            setFile(acceptedFiles[0])
        }
    }, [])

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, maxFiles: 1 })

    // AI Analysis Handler
    const handleAnalyze = async () => {
        if (!file) return

        // Only allow PDF files for analysis
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('KI-Analyse funktioniert nur mit PDF-Dateien.')
            return
        }

        setAnalyzing(true)
        try {
            const formData = new FormData()
            formData.append('file', file)

            const response = await api.post('/contracts/analyze', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            })

            const data = response.data

            // Auto-fill form fields from AI response
            if (data.title) setTitle(data.title)
            if (data.description) setDescription(data.description)
            if (data.value !== null && data.value !== undefined) {
                setValue(formatGermanNumber(data.value))
            }
            if (data.annual_value !== null && data.annual_value !== undefined) {
                setAnnualValue(formatGermanNumber(data.annual_value))
            }
            if (data.start_date) setStartDate(data.start_date)
            if (data.end_date) setEndDate(data.end_date)
            if (data.notice_period !== null && data.notice_period !== undefined) {
                setNoticePeriod(data.notice_period.toString())
            } else {
                setNoticePeriod('')
            }
            if (data.tags && data.tags.length > 0) setTags(data.tags.join(', '))

        } catch (error: any) {
            console.error('AI Analysis failed', error)
            const detail = error.response?.data?.detail || error.message || 'Unbekannter Fehler'
            alert(`KI-Analyse fehlgeschlagen: ${detail}`)
        } finally {
            setAnalyzing(false)
        }
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        // File is required only for new contracts
        if (!initialData && !file) return
        if (!title) return

        setUploading(true)

        try {
            const parsedValue = value ? parseGermanNumber(value) : null
            const parsedAnnualValue = annualValue ? parseGermanNumber(annualValue) : null

            if (value && (parsedValue === null || parsedValue < 0)) {
                alert('Bitte geben Sie einen gültigen nicht-negativen Gesamtwert ein.')
                return
            }

            if (annualValue && (parsedAnnualValue === null || parsedAnnualValue < 0)) {
                alert('Bitte geben Sie einen gültigen nicht-negativen jährlichen Preis ein.')
                return
            }

            const formData = new FormData()
            if (file) formData.append('file', file)
            formData.append('title', title)
            formData.append('description', description || '')
            formData.append('value', parsedValue !== null ? parsedValue.toString() : '')
            formData.append('annual_value', parsedAnnualValue !== null ? parsedAnnualValue.toString() : '')
            formData.append('notice_period', noticePeriod || '')
            formData.append('tags', tags || '')
            formData.append('start_date', startDate ? new Date(startDate).toISOString() : '')
            formData.append('end_date', endDate ? new Date(endDate).toISOString() : '')

            if (initialData) {
                // Edit Mode: PUT request (FormData)
                await api.put(`/contracts/${initialData.id}`, formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                })
            } else {
                // Create Mode: POST request (FormData)
                await api.post('/contracts', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                })
            }

            queryClient.invalidateQueries(['contracts'])
            onClose()
            // Reset form
            setFile(null)
            setTitle('')
            setDescription('')
            setValue('')
            setAnnualValue('')
            setTags('')
            setNoticePeriod('')
            setStartDate('')
            setEndDate('')
        } catch (error: any) {
            console.error('Operation failed', error)
            const msg = error.response?.data?.detail || error.message || "Unknown error";
            alert(`Operation failed: ${msg}`);
        } finally {
            setUploading(false)
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
                        <div className="bg-gray-900 border border-gray-700 w-full max-w-xl rounded-2xl shadow-2xl pointer-events-auto flex flex-col max-h-[90vh] overflow-y-auto">
                            <div className="flex justify-between items-center p-6 border-b border-gray-800">
                                <h3 className="text-xl font-semibold text-white">{initialData ? 'Vertrag bearbeiten' : 'Vertrag hochladen'}</h3>
                                <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                                    <FiX size={24} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmit} className="p-6 space-y-4">
                                <div {...getRootProps()} className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${isDragActive ? 'border-blue-500 bg-blue-500/10' : 'border-gray-700 hover:border-gray-600 bg-gray-800/50'}`}>
                                    <input {...getInputProps()} />
                                    <FiUploadCloud className="mx-auto text-4xl text-gray-400 mb-3" />
                                    {file ? (
                                        <p className="text-blue-400 font-medium">{file.name}</p>
                                    ) : (
                                        <p className="text-gray-400">
                                            {initialData ? 'Neue Datei hier ablegen zum Ersetzen (Optional)' : 'Datei hier ablegen oder klicken'}
                                        </p>
                                    )}
                                </div>

                                {/* AI Analyze Button - Only show for new contracts with PDF files */}
                                {file && !initialData && file.name.toLowerCase().endsWith('.pdf') && (
                                    <button
                                        type="button"
                                        onClick={handleAnalyze}
                                        disabled={analyzing || uploading}
                                        className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white py-3 rounded-xl font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-purple-500/25"
                                    >
                                        {analyzing ? (
                                            <>
                                                <span className="animate-spin"><FiZap /></span>
                                                <span>KI analysiert Vertrag...</span>
                                            </>
                                        ) : (
                                            <>
                                                <FiZap className="text-yellow-300" />
                                                <span>Mit KI automatisch ausfüllen</span>
                                            </>
                                        )}
                                    </button>
                                )}

                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Titel</label>
                                    <input type="text" value={title} onChange={e => setTitle(e.target.value)} className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" required />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-1">Gesamtwert (€)</label>
                                        <input
                                            type="text"
                                            value={value}
                                            onChange={e => setValue(e.target.value)}
                                            placeholder="z.B. 17.100"
                                            className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-1">Jährlicher Preis (€)</label>
                                        <input
                                            type="text"
                                            value={annualValue}
                                            onChange={e => setAnnualValue(e.target.value)}
                                            placeholder="z.B. 2.500"
                                            className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Beschreibung</label>
                                    <textarea value={description} onChange={e => setDescription(e.target.value)} className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" rows={2} />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Tags (kommagetrennt)</label>
                                    <input type="text" value={tags} onChange={e => setTags(e.target.value)} placeholder="Software, SaaS, 2024" className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-1">Startdatum</label>
                                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-1">Enddatum</label>
                                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-1">Kündigungsfrist (Tage)</label>
                                    <input type="number" value={noticePeriod} onChange={e => setNoticePeriod(e.target.value)} placeholder="30" className="w-full bg-gray-800 border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500" />
                                </div>

                                <div className="pt-4">
                                    <button type="submit" disabled={uploading} className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 rounded-lg transition-colors disabled:opacity-50">
                                        {uploading ? (initialData ? 'Speichern...' : 'Hochladen...') : (initialData ? 'Änderungen speichern' : 'Vertrag hochladen')}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    )
}

export default UploadModal
