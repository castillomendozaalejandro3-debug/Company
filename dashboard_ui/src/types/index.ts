export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

export interface SystemMetrics {
  cpu_usage: number;
  memory_usage_percent: number;
  total_memory: number;
  used_memory: number;
  disks: DiskInfo[];
}

export interface DiskInfo {
  name: string;
  total_space: number;
  used_space: number;
  usage_percent: number;
}

export interface LogEntry {
  source: string;
  line: string;
  level?: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  timestamp?: string;
}

export interface AgentStatus {
  name: string;
  status: 'active' | 'inactive' | 'error';
  lastActivity?: Date;
}
