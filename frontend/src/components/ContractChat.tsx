import React, { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FiX, FiSend, FiMessageCircle } from 'react-icons/fi'
import ReactMarkdown from 'react-markdown'
import { buildApiUrl, ensureCsrfToken } from '../api'

interface ContractChatProps {
    isOpen: boolean
    onClose: () => void
    contractId: number
    contractTitle: string
}

interface Message {
    role: 'user' | 'assistant'
    content: string
    isStreaming?: boolean
}

const ContractChat: React.FC<ContractChatProps> = ({ isOpen, onClose, contractId, contractTitle }) => {
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    const handleSend = async () => {
        if (!input.trim() || loading) return

        const userMessage = input.trim()
        setInput('')
        setMessages(prev => [...prev, { role: 'user', content: userMessage }])
        setLoading(true)

        // Add empty assistant message that will be filled by stream
        setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }])

        try {
            const csrfToken = await ensureCsrfToken()
            // Use streaming endpoint with fetch
            const response = await fetch(buildApiUrl(`/contracts/${contractId}/chat/stream`), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
                },
                body: JSON.stringify({ question: userMessage }),
                credentials: 'include'
            })

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`)
            }

            const reader = response.body?.getReader()
            const decoder = new TextDecoder()

            if (!reader) {
                throw new Error('No response body')
            }

            let fullContent = ''
            let pending = ''

            const applyAssistantContent = () => {
                setMessages(prev => {
                    const newMessages = [...prev]
                    const lastIdx = newMessages.length - 1
                    if (lastIdx >= 0 && newMessages[lastIdx].role === 'assistant') {
                        newMessages[lastIdx] = {
                            ...newMessages[lastIdx],
                            content: fullContent
                        }
                    }
                    return newMessages
                })
            }

            const handleSseEvent = (event: string) => {
                const dataLines = event
                    .split('\n')
                    .filter(line => line.startsWith('data: '))
                    .map(line => line.slice(6))

                for (const jsonData of dataLines) {
                    const data = JSON.parse(jsonData)

                    if (data === '[DONE]') {
                        continue
                    }

                    if (typeof data === 'string' && data.startsWith('[ERROR]')) {
                        throw new Error(data.slice(8))
                    }

                    if (typeof data === 'string') {
                        fullContent += data
                        applyAssistantContent()
                    }
                }
            }

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                pending += decoder.decode(value, { stream: true })
                const events = pending.split('\n\n')
                pending = events.pop() ?? ''

                for (const event of events) {
                    if (event.trim()) {
                        handleSseEvent(event)
                    }
                }
            }

            pending += decoder.decode()
            if (pending.trim()) {
                handleSseEvent(pending)
            }

            // Mark streaming as complete
            setMessages(prev => {
                const newMessages = [...prev]
                const lastIdx = newMessages.length - 1
                if (lastIdx >= 0 && newMessages[lastIdx].role === 'assistant') {
                    newMessages[lastIdx] = {
                        ...newMessages[lastIdx],
                        isStreaming: false
                    }
                }
                return newMessages
            })

        } catch (error: any) {
            console.error('Chat failed', error)
            const detail = error.message || 'Unbekannter Fehler'

            // Update the last message with error
            setMessages(prev => {
                const newMessages = [...prev]
                const lastIdx = newMessages.length - 1
                if (lastIdx >= 0 && newMessages[lastIdx].role === 'assistant') {
                    newMessages[lastIdx] = {
                        role: 'assistant',
                        content: `Fehler: ${detail}`,
                        isStreaming: false
                    }
                }
                return newMessages
            })
        } finally {
            setLoading(false)
        }
    }

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40"
                        onClick={onClose}
                    />

                    {/* Chat Modal */}
                    <motion.div
                        initial={{ opacity: 0, x: 100 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 100 }}
                        className="fixed right-0 top-0 bottom-0 w-full max-w-md z-50 flex flex-col bg-gray-900 border-l border-gray-700 shadow-2xl"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between p-4 border-b border-gray-800">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-purple-600/20 rounded-lg">
                                    <FiMessageCircle className="text-purple-400" size={20} />
                                </div>
                                <div>
                                    <h3 className="text-white font-semibold">Vertrags-Chat</h3>
                                    <p className="text-gray-400 text-sm truncate max-w-[200px]">{contractTitle}</p>
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="text-gray-400 hover:text-white transition-colors p-2"
                            >
                                <FiX size={24} />
                            </button>
                        </div>

                        {/* Messages Area */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            {messages.length === 0 && (
                                <div className="text-center text-gray-500 py-8">
                                    <FiMessageCircle className="mx-auto text-4xl mb-3 opacity-50" />
                                    <p>Stelle eine Frage zum Vertrag</p>
                                    <div className="mt-4 space-y-2">
                                        <button
                                            onClick={() => setInput('Was sind die wichtigsten Kündigungsbedingungen?')}
                                            className="block w-full text-left px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
                                        >
                                            💡 Was sind die wichtigsten Kündigungsbedingungen?
                                        </button>
                                        <button
                                            onClick={() => setInput('Fasse den Vertrag kurz zusammen')}
                                            className="block w-full text-left px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
                                        >
                                            💡 Fasse den Vertrag kurz zusammen
                                        </button>
                                        <button
                                            onClick={() => setInput('Welche Kosten entstehen?')}
                                            className="block w-full text-left px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
                                        >
                                            💡 Welche Kosten entstehen?
                                        </button>
                                    </div>
                                </div>
                            )}

                            {messages.map((message, index) => (
                                <div
                                    key={index}
                                    className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                >
                                    <div
                                        className={`max-w-[85%] rounded-2xl px-4 py-3 ${message.role === 'user'
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-800 text-gray-100 border border-gray-700'
                                            }`}
                                    >
                                        {message.role === 'user' ? (
                                            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                                        ) : (
                                            <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-headings:my-2 prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-600">
                                                <ReactMarkdown>{message.content}</ReactMarkdown>
                                                {message.isStreaming && (
                                                    <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-1" />
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {loading && messages[messages.length - 1]?.content === '' && (
                                <div className="flex justify-start">
                                    <div className="bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3">
                                        <div className="flex gap-1">
                                            <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Scroll anchor */}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Input Area */}
                        <div className="p-4 border-t border-gray-800">
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyPress={handleKeyPress}
                                    placeholder="Frage zum Vertrag stellen..."
                                    className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors"
                                    disabled={loading}
                                />
                                <button
                                    onClick={handleSend}
                                    disabled={!input.trim() || loading}
                                    className="px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <FiSend size={20} />
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    )
}

export default ContractChat
