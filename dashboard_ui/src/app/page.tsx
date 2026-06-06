'use client'

import { useState, useEffect } from 'react'
import CommandPanel from './components/CommandPanel'
import SystemMetrics from './components/SystemMetrics'
import SecurityLogs from './components/SecurityLogs'

export default function Home() {
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    // Verificar conexión al cargar
    fetch('/api/v1/health')
      .then(res => res.json())
      .then(data => {
        setIsConnected(data.python_server)
      })
      .catch(() => setIsConnected(false))
  }, [])

  return (
    <main className="min-h-screen bg-slate-950 p-4 md:p-8">
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-cyan-400 glow-cyan inline-block">
              HELIOS AI
            </h1>
            <p className="text-slate-400 mt-1">Centro de Comando Multi-Agente</p>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-emerald-500 glow-green' : 'bg-red-500 glow-red'}`} />
            <span className="text-sm text-slate-400">
              {isConnected ? 'Sistema Conectado' : 'Desconectado'}
            </span>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Panel de Comandos - Ocupa 2 columnas */}
        <div className="lg:col-span-2">
          <CommandPanel />
        </div>

        {/* Panel de Métricas */}
        <div>
          <SystemMetrics />
        </div>

        {/* Panel de Logs - Ocupa todo el ancho abajo */}
        <div className="lg:col-span-3">
          <SecurityLogs />
        </div>
      </div>
    </main>
  )
}
