import React, { useCallback, useEffect, useState } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { AnimatePresence, motion } from 'framer-motion'
import { FiCheck, FiFileText, FiUploadCloud, FiX, FiZap } from 'react-icons/fi'
import { useQueryClient } from '@tanstack/react-query'
import api from '../api'
import { formatGermanNumber, parseGermanNumber } from '../utils/formatUtils'

interface UploadModalProps {
    isOpen: boolean
    onClose: () => void
    initialData?: any
    documentType?: 'contract' | 'invoice'
}

const MAX_UPLOAD_SIZE = 10 * 1024 * 1024
const ACCEPTED_UPLOAD_TYPES = {
    'application/pdf': ['.pdf'],
    'image/png': ['.png'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'text/plain': ['.txt'],
}

const formatUploadSize = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`
const dateForInput = (value?: string) => {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${date.getFullYear()}-${month}-${day}`
}

const UploadModal: React.FC<UploadModalProps> = ({ isOpen, onClose, initialData, documentType = 'contract' }) => {
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
    const [fileError, setFileError] = useState('')
    const queryClient = useQueryClient()

    const isInvoice = (initialData?.document_type ?? documentType) === 'invoice'
    const documentLabel = isInvoice ? 'Rechnung' : 'Vertrag'

    useEffect(() => {
        if (!isOpen) return
        setTitle(initialData?.title || '')
        setDescription(initialData?.description || '')
        setValue(initialData?.value != null ? formatGermanNumber(initialData.value) : '')
        setAnnualValue(initialData?.annual_value != null ? formatGermanNumber(initialData.annual_value) : '')
        setTags(initialData?.tags?.map((tag: any) => tag.name).join(', ') || '')
        setNoticePeriod(initialData?.notice_period?.toString() || '')
        setStartDate(dateForInput(initialData?.start_date))
        setEndDate(dateForInput(initialData?.end_date))
        setFile(null)
        setFileError('')
    }, [isOpen, initialData])

    const onDrop = useCallback((acceptedFiles: File[]) => {
        if (!acceptedFiles.length) return
        setFileError('')
        setFile(acceptedFiles[0])
    }, [])

    const onDropRejected = useCallback((rejections: FileRejection[]) => {
        const firstError = rejections[0]?.errors[0]
        if (!firstError) return
        if (firstError.code === 'file-too-large') setFileError(`Die Datei darf maximal ${formatUploadSize(MAX_UPLOAD_SIZE)} groß sein.`)
        else if (firstError.code === 'file-invalid-type') setFileError('Bitte laden Sie eine PDF-, Bild- oder Textdatei hoch.')
        else setFileError(firstError.message)
        setFile(null)
    }, [])

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        onDropRejected,
        accept: ACCEPTED_UPLOAD_TYPES,
        maxFiles: 1,
        maxSize: MAX_UPLOAD_SIZE,
    })

    const handleAnalyze = async () => {
        if (!file) return
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('KI-Analyse funktioniert nur mit PDF-Dateien.')
            return
        }
        setAnalyzing(true)
        try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('document_type', isInvoice ? 'invoice' : 'contract')
            const { data } = await api.post('/contracts/analyze', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
            if (data.title) setTitle(data.title)
            if (data.description) setDescription(data.description)
            if (data.value != null) setValue(formatGermanNumber(data.value))
            if (data.annual_value != null) setAnnualValue(formatGermanNumber(data.annual_value))
            if (data.start_date) setStartDate(data.start_date)
            if (data.end_date) setEndDate(data.end_date)
            setNoticePeriod(data.notice_period != null ? data.notice_period.toString() : '')
            if (data.tags?.length) setTags(data.tags.join(', '))
        } catch (error: any) {
            const detail = error.response?.data?.detail || error.message || 'Unbekannter Fehler'
            alert(`KI-Analyse fehlgeschlagen: ${detail}`)
        } finally {
            setAnalyzing(false)
        }
    }

    const resetAndClose = () => {
        setFile(null)
        setTitle('')
        setDescription('')
        setValue('')
        setAnnualValue('')
        setTags('')
        setNoticePeriod('')
        setStartDate('')
        setEndDate('')
        setFileError('')
        onClose()
    }

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault()
        if ((!initialData && !file) || !title) return
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
            if (!initialData) formData.append('document_type', isInvoice ? 'invoice' : 'contract')

            if (initialData) await api.put(`/contracts/${initialData.id}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
            else await api.post('/contracts', formData, { headers: { 'Content-Type': 'multipart/form-data' } })

            await Promise.all([
                queryClient.invalidateQueries(['contracts']),
                queryClient.invalidateQueries(['invoices']),
                queryClient.invalidateQueries(['workspace-documents']),
            ])
            resetAndClose()
        } catch (error: any) {
            const message = error.response?.data?.detail || error.message || 'Unbekannter Fehler'
            alert(`Vorgang fehlgeschlagen: ${message}`)
        } finally {
            setUploading(false)
        }
    }

    const FieldLabel = ({ children }: { children: React.ReactNode }) => <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.14em] text-white/38">{children}</span>

    return <AnimatePresence>
        {isOpen && <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[80] bg-black/75 backdrop-blur-md" onClick={onClose} />
            <motion.div initial={{ opacity: 0, scale: 0.97, y: 18 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97, y: 18 }} transition={{ duration: 0.22 }} className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center p-2 sm:p-5">
                <div className="pointer-events-auto flex max-h-[96vh] w-full max-w-4xl flex-col overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#0c0f0d] shadow-[0_36px_120px_rgba(0,0,0,0.65)]">
                    <header className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4 sm:px-7">
                        <div className="flex items-center gap-3">
                            <div className={`flex h-10 w-10 items-center justify-center rounded-2xl ${isInvoice ? 'bg-[#7397ff]/10 text-[#9ab1ff]' : 'bg-[#b8f15a]/10 text-[#b8f15a]'}`}><FiFileText /></div>
                            <div><p className="eyebrow">{initialData ? 'Document review' : 'New intake'}</p><h2 className="mt-1 text-lg font-semibold">{initialData ? `${documentLabel} bearbeiten` : `${documentLabel} erfassen`}</h2></div>
                        </div>
                        <button onClick={onClose} className="icon-btn"><FiX size={18} /></button>
                    </header>

                    <form onSubmit={handleSubmit} className="overflow-y-auto">
                        <div className="grid lg:grid-cols-[0.82fr_1.18fr]">
                            <aside className="border-b border-white/[0.07] bg-black/15 p-5 sm:p-7 lg:border-b-0 lg:border-r">
                                <p className="eyebrow">01 · Quelldatei</p>
                                <div {...getRootProps()} className={`mt-4 flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed p-6 text-center transition-all ${isDragActive ? 'border-[#b8f15a]/55 bg-[#b8f15a]/[0.07]' : file ? 'border-emerald-300/25 bg-emerald-300/[0.035]' : 'border-white/[0.12] bg-white/[0.018] hover:border-white/25 hover:bg-white/[0.03]'}`}>
                                    <input {...getInputProps()} />
                                    <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-2xl ${file ? 'bg-emerald-300/10 text-emerald-200' : 'bg-white/[0.05] text-white/45'}`}>{file ? <FiCheck size={22} /> : <FiUploadCloud size={23} />}</div>
                                    {file ? <><p className="max-w-full truncate text-sm font-semibold text-emerald-100">{file.name}</p><p className="mt-2 text-xs text-white/34">{(file.size / 1024 / 1024).toFixed(1)} MB · Klicken zum Ersetzen</p></> : <><p className="text-sm font-semibold">{initialData ? 'Neue Datei ablegen' : `${documentLabel} hier ablegen`}</p><p className="mt-2 max-w-56 text-xs leading-5 text-white/34">PDF, PNG, JPG oder TXT · maximal {formatUploadSize(MAX_UPLOAD_SIZE)}</p></>}
                                </div>
                                {fileError && <p className="mt-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.06] px-3 py-2 text-xs text-rose-200" role="alert">{fileError}</p>}

                                {file && !initialData && file.name.toLowerCase().endsWith('.pdf') && <button type="button" onClick={handleAnalyze} disabled={analyzing || uploading} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl border border-[#977dff]/25 bg-[#977dff]/[0.08] px-4 py-3 text-sm font-semibold text-[#c9bcff] transition-colors hover:bg-[#977dff]/[0.13] disabled:opacity-50">
                                    <FiZap className={analyzing ? 'animate-pulse' : ''} /> {analyzing ? `KI analysiert ${documentLabel} …` : 'Mit KI automatisch ausfüllen'}
                                </button>}

                                <div className="mt-7 space-y-3 text-xs text-white/36">
                                    <p className="eyebrow">So funktioniert’s</p>
                                    <p className="flex gap-2"><span className="text-[#b8f15a]">01</span> Datei sicher hochladen</p>
                                    <p className="flex gap-2"><span className="text-[#b8f15a]">02</span> Daten per KI extrahieren</p>
                                    <p className="flex gap-2"><span className="text-[#b8f15a]">03</span> Prüfen und speichern</p>
                                </div>
                            </aside>

                            <section className="p-5 sm:p-7">
                                <div className="mb-5 flex items-center justify-between"><p className="eyebrow">02 · Details prüfen</p><span className="chip">{isInvoice ? 'Invoice' : 'Contract'}</span></div>
                                <div className="space-y-5">
                                    <label className="block"><FieldLabel>{isInvoice ? 'Lieferant / Rechnungstitel' : 'Vertragstitel'}</FieldLabel><input type="text" value={title} onChange={(event) => setTitle(event.target.value)} className="field" placeholder={isInvoice ? 'z. B. Telekom · Juni 2026' : 'z. B. Cloud Hosting Enterprise'} required /></label>
                                    <div className={`grid gap-4 ${isInvoice ? '' : 'sm:grid-cols-2'}`}>
                                        <label className="block"><FieldLabel>{isInvoice ? 'Rechnungsbetrag (€)' : 'Gesamtwert (€)'}</FieldLabel><input type="text" value={value} onChange={(event) => setValue(event.target.value)} placeholder="z. B. 17.100,00" className="field" /></label>
                                        {!isInvoice && <label className="block"><FieldLabel>Jährlicher Preis (€)</FieldLabel><input type="text" value={annualValue} onChange={(event) => setAnnualValue(event.target.value)} placeholder="z. B. 2.500,00" className="field" /></label>}
                                    </div>
                                    <label className="block"><FieldLabel>Beschreibung</FieldLabel><textarea value={description} onChange={(event) => setDescription(event.target.value)} className="field min-h-20 resize-y" placeholder="Worum geht es in diesem Dokument?" rows={3} /></label>
                                    <label className="block"><FieldLabel>Tags</FieldLabel><input type="text" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Software, SaaS, 2026" className="field" /><span className="mt-2 block text-[11px] text-white/28">Mehrere Tags mit Komma trennen.</span></label>
                                    <div className={`grid gap-4 ${isInvoice ? '' : 'sm:grid-cols-2'}`}>
                                        <label className="block"><FieldLabel>{isInvoice ? 'Rechnungsdatum' : 'Startdatum'}</FieldLabel><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="field [color-scheme:dark]" /></label>
                                        {!isInvoice && <label className="block"><FieldLabel>Enddatum</FieldLabel><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="field [color-scheme:dark]" /></label>}
                                    </div>
                                    {!isInvoice && <label className="block"><FieldLabel>Kündigungsfrist (Tage)</FieldLabel><input type="number" min="0" value={noticePeriod} onChange={(event) => setNoticePeriod(event.target.value)} placeholder="30" className="field" /></label>}
                                </div>
                            </section>
                        </div>

                        <footer className="flex flex-col-reverse gap-2 border-t border-white/[0.07] bg-black/15 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
                            <p className="text-xs text-white/28">Pflichtfelder werden vor dem Speichern geprüft.</p>
                            <div className="flex gap-2"><button type="button" onClick={onClose} className="btn-ghost">Abbrechen</button><button type="submit" disabled={uploading || (!initialData && !file)} className="btn-primary min-w-40"><FiUploadCloud /> {uploading ? (initialData ? 'Speichern …' : 'Hochladen …') : initialData ? 'Änderungen speichern' : `${documentLabel} hochladen`}</button></div>
                        </footer>
                    </form>
                </div>
            </motion.div>
        </>}
    </AnimatePresence>
}

export default UploadModal
