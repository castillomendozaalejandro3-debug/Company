const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export interface ExecuteRequest {
  request: string;
  user_id?: string;
  context?: Record<string, any>;
}

export interface ExecuteResponse {
  success: boolean;
  message: string;
  data?: any;
  error?: string;
}

export interface LogEntry {
  source: string;
  line: string;
}

export interface SystemHealth {
  status: string;
  python_server: boolean;
  rust_core: boolean;
  orchestrator: boolean;
  details: Record<string, any>;
}

export async function executeCommand(data: ExecuteRequest): Promise<ExecuteResponse> {
  const response = await fetch(`${API_BASE_URL}/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Error HTTP: ${response.status}`);
  }

  return response.json();
}

export async function getHealth(): Promise<SystemHealth> {
  const response = await fetch(`${API_BASE_URL}/health`);
  
  if (!response.ok) {
    throw new Error(`Error HTTP: ${response.status}`);
  }

  return response.json();
}

export async function getLogs(lines: number = 50): Promise<{ logs: LogEntry[] }> {
  const response = await fetch(`${API_BASE_URL}/logs?lines=${lines}`);
  
  if (!response.ok) {
    throw new Error(`Error HTTP: ${response.status}`);
  }

  return response.json();
}
