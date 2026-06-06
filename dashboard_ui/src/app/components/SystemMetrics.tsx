'use client'

import { useState, useEffect } from 'react'
import { Cpu, MemoryStick, HardDrive, RefreshCw } from 'lucide-react'

interface MetricsData {
  cpu_usage: number;
  memory_usage_percent: number;
  total_memory: number;
  used_memory: number;
  disks: Array<{
    name: string;
    usage_percent: number;
  }>;
}

export default function SystemMetrics() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchMetrics = async () => {
    try {
      // En producción, esto llamaría a la API real
      // Por ahora usamos datos simulados
      const simulatedMetrics: MetricsData = {
        cpu_usage: Math.random() * 30 + 10,
        memory_usage_percent: Math.random() * 20 + 40,
        total_memory: 16 * 1024 * 1024 * 1024,
        used_memory: 8 * 1024 * 1024 * 1024,
        disks: [
          { name: 'C:', usage_percent: 45 },
          { name: 'D:', usage_percent: 30 },
        ],
      }
      setMetrics(simulatedMetrics)
      setError(null)
    } catch (err) {
      setError('No se pudo obtener las métricas')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMetrics()
    const interval = setInterval(fetchMetrics, 5000)
    return () => clearInterval(interval)
  }, [])

  const formatBytes = (bytes: number) => {
    const gb = bytes / (1024 * 1024 * 1024)
    return `${gb.toFixed(1)} GB`
  }

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
      <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Métricas del Sistema</h2>
        <button
          onClick={fetchMetrics}
          className="text-cyan-400 hover:text-cyan-300 transition-colors"
          title="Actualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {error ? (
          <div className="text-red-400 text-sm">{error}</div>
        ) : loading ? (
          <div className="text-slate-500 text-sm">Cargando...</div>
        ) : metrics ? (
          <>
            {/* CPU */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span className="text-sm text-slate-300">CPU</span>
                <span className="ml-auto text-sm font-mono text-cyan-400">
                  {metrics.cpu_usage.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all duration-500"
                  style={{ width: `${Math.min(metrics.cpu_usage, 100)}%` }}
                />
              </div>
            </div>

            {/* RAM */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <MemoryStick className="w-4 h-4 text-emerald-400" />
                <span className="text-sm text-slate-300">RAM</span>
                <span className="ml-auto text-sm font-mono text-emerald-400">
                  {formatBytes(metrics.used_memory)} / {formatBytes(metrics.total_memory)}
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                  style={{ width: `${Math.min(metrics.memory_usage_percent, 100)}%` }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-1 text-right">
                {metrics.memory_usage_percent.toFixed(1)}% usado
              </div>
            </div>

            {/* Discos */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <HardDrive className="w-4 h-4 text-purple-400" />
                <span className="text-sm text-slate-300">Discos</span>
              </div>
              <div className="space-y-2">
                {metrics.disks.map((disk, idx) => (
                  <div key={idx}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-400">{disk.name}</span>
                      <span className="text-purple-400">{disk.usage_percent}%</span>
                    </div>
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-purple-600 to-purple-400"
                        style={{ width: `${disk.usage_percent}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
