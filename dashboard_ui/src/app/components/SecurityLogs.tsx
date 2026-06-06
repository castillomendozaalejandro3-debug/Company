'use client'

import { useState, useEffect } from 'react'
import { getLogs } from '../../lib/api'
import { LogEntry } from '../../types'
import { Shield, AlertTriangle, CheckCircle, XCircle, Activity } from 'lucide-react'

export default function SecurityLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)

  const fetchLogs = async () => {
    try {
      // Datos simulados para demostración
      const simulatedLogs: LogEntry[] = [
        { source: 'security_shield.log', line: '[2024-01-15 10:23:45] [INFO] Escaneo completado - Sin amenazas detectadas' },
        { source: 'orchestrator.log', line: '[2024-01-15 10:22:30] [INFO] Tarea clasificada: pc_control' },
        { source: 'pentest_agent.log', line: '[2024-01-15 10:20:15] [WARNING] Target no autorizado bloqueado: 8.8.8.8' },
        { source: 'pc_controller.log', line: '[2024-01-15 10:18:00] [INFO] Aplicación abierta: Chrome' },
        { source: 'visual_agent.log', line: '[2024-01-15 10:15:45] [INFO] Captura de pantalla realizada en monitor 2' },
        { source: 'security_shield.log', line: '[2024-01-15 10:12:30] [CRITICAL] Intento de acceso a /etc/shadow bloqueado' },
      ]
      setLogs(simulatedLogs)
    } catch (error) {
      console.error('Error fetching logs:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
    const interval = setInterval(fetchLogs, 3000)
    return () => clearInterval(interval)
  }, [])

  const getLogIcon = (line: string) => {
    if (line.includes('CRITICAL') || line.includes('ERROR')) {
      return <XCircle className="w-4 h-4 text-red-500" />
    }
    if (line.includes('WARNING')) {
      return <AlertTriangle className="w-4 h-4 text-yellow-500" />
    }
    if (line.includes('INFO')) {
      return <CheckCircle className="w-4 h-4 text-emerald-500" />
    }
    return <Activity className="w-4 h-4 text-slate-500" />
  }

  const getLogColor = (line: string) => {
    if (line.includes('CRITICAL') || line.includes('ERROR')) {
      return 'text-red-400 bg-red-950/30 border-red-900'
    }
    if (line.includes('WARNING')) {
      return 'text-yellow-400 bg-yellow-950/30 border-yellow-900'
    }
    if (line.includes('INFO')) {
      return 'text-emerald-400 bg-emerald-950/30 border-emerald-900'
    }
    return 'text-slate-400 bg-slate-800/50 border-slate-700'
  }

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
      <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center gap-2">
        <Shield className="w-5 h-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-white">Logs de Seguridad</h2>
      </div>

      <div className="h-64 overflow-y-auto p-4 space-y-2 console-font">
        {loading ? (
          <div className="text-slate-500 text-sm">Cargando logs...</div>
        ) : logs.length === 0 ? (
          <div className="text-slate-500 text-sm text-center">No hay logs recientes</div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              className={`flex items-start gap-2 p-2 rounded border ${getLogColor(log.line)} text-xs`}
            >
              <span className="mt-0.5">{getLogIcon(log.line)}</span>
              <div className="flex-1 min-w-0">
                <span className="font-semibold opacity-75 mr-2">[{log.source}]</span>
                <span className="break-all">{log.line}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
