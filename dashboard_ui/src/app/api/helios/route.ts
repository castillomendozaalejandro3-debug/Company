import { NextRequest, NextResponse } from 'next/server';

const KERNEL_DAEMON_URL = process.env.KERNEL_DAEMON_URL || 'http://localhost:8080/api/v1/commands';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { command, payload, priority = 'normal' } = body;

    if (!command) {
      return NextResponse.json(
        { error: 'Command is required' },
        { status: 400 }
      );
    }

    // Enviar comando al KernelDaemon en lugar de los agentes antiguos
    const response = await fetch(KERNEL_DAEMON_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Command-Source': 'dashboard-ui',
        'X-Priority': priority,
      },
      body: JSON.stringify({
        command,
        payload: payload || {},
        timestamp: new Date().toISOString(),
        source: 'frontend',
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage = `KernelDaemon responded with status ${response.status}`;
      
      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.error || errorJson.message || errorMessage;
      } catch {
        errorMessage = errorText || errorMessage;
      }

      return NextResponse.json(
        { error: errorMessage, status: response.status },
        { status: response.status }
      );
    }

    const result = await response.json();

    return NextResponse.json({
      success: true,
      data: result,
      message: 'Command sent to KernelDaemon successfully',
    });
  } catch (error) {
    console.error('Error forwarding command to KernelDaemon:', error);
    
    if (error instanceof Error) {
      if (error.message.includes('fetch failed') || error.message.includes('ECONNREFUSED')) {
        return NextResponse.json(
          { 
            error: 'Cannot connect to KernelDaemon. Ensure the service is running.',
            details: error.message 
          },
          { status: 503 }
        );
      }
      
      return NextResponse.json(
        { error: 'Failed to process command', details: error.message },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { error: 'An unexpected error occurred' },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    // Obtener estado del KernelDaemon
    const statusUrl = KERNEL_DAEMON_URL.replace('/commands', '/status');
    
    const response = await fetch(statusUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: 'KernelDaemon status check failed', status: response.status },
        { status: response.status }
      );
    }

    const status = await response.json();

    return NextResponse.json({
      success: true,
      data: status,
      message: 'KernelDaemon is operational',
    });
  } catch (error) {
    console.error('Error checking KernelDaemon status:', error);
    
    return NextResponse.json(
      { 
        error: 'Cannot reach KernelDaemon',
        details: error instanceof Error ? error.message : 'Unknown error',
        kernel_daemon_url: KERNEL_DAEMON_URL
      },
      { status: 503 }
    );
  }
}
