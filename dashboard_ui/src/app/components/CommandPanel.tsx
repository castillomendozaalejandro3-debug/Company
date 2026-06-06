'use client'

import { useState } from 'react'
import { executeCommand } from '../../lib/api'
import { Message } from '../../types'
import { Send, Terminal, Loader2 } from 'lucide-react'

export default function CommandPanel() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await executeCommand({
        request: input,
        user_id: 'dashboard-user',
      })

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message || JSON.stringify(response.data),
        timestamp: new Date(),
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'system',
        content: `Error: ${error instanceof Error ? error.message : 'Error desconocido'}`,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg glow-cyan overflow-hidden">
      <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center gap-2">
        <Terminal className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-white">Comandos</h2>
      </div>

      <div className="h-96 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-slate-500 text-center mt-20">
            <p>Escribe un comando para comenzar</p>
            <p className="text-sm mt-2">Ej: &quot;escanea 127.0.0.1&quot;, &quot;abre Chrome&quot;, &quot;obten métricas del sistema&quot;</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg p-3 ${
                  msg.role === 'user'
                    ? 'bg-cyan-600 text-white'
                    : msg.role === 'system'
                    ? 'bg-red-900 text-red-100'
                    : 'bg-slate-700 text-slate-100'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                <span className="text-xs opacity-70 mt-1 block">
                  {msg.timestamp.toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-slate-700 rounded-lg p-3 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
              <span className="text-slate-300 text-sm">Procesando...</span>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-700 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe tu comando..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-4 py-2 text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-600 text-white px-4 py-2 rounded transition-colors flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">Enviar</span>
          </button>
        </div>
      </form>
    </div>
  )
}
