# Helios AI Kernel - Documentación de API
# Helios AI Kernel - API Documentation

**Versión:** 1.0.0  
**Base URL:** `https://api.helios-enterprise.com/v1`  
**Autenticación:** Bearer Token (JWT)

---

## 1. Autenticación y Autorización
## 1. Authentication & Authorization

### 1.1 Obtener Token / Get Token

```http
POST /auth/token
Content-Type: application/json

{
  "username": "tu_usuario",
  "password": "tu_password"
}
```

**Respuesta / Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."
}
```

### 1.2 Usar Token / Using Token

Incluir en todos los requests:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 1.3 Refresh Token / Refresh Token

```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."
}
```

---

## 2. Endpoints Principales / Main Endpoints

### 2.1 Chat / Conversación

#### POST /chat

Enviar mensaje y recibir respuesta del asistente.

```http
POST /chat
Content-Type: application/json
Authorization: Bearer {token}

{
  "message": "¿Cuáles son mis tareas pendientes?",
  "channel": "whatsapp",
  "session_id": "sess_abc123",
  "context": {
    "user_timezone": "America/Mexico_City",
    "language": "es"
  }
}
```

**Parámetros / Parameters:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `message` | string | Sí | Mensaje del usuario |
| `channel` | string | No | Canal de origen (whatsapp, instagram, web) |
| `session_id` | string | No | ID de sesión para mantener contexto |
| `context` | object | No | Contexto adicional (timezone, language, etc.) |

**Respuesta Exitosa / Success Response (200 OK):**
```json
{
  "status": "success",
  "data": {
    "response": "Tienes 3 tareas pendientes:\n1. Revisar informe Q3 (Vence: mañana)\n2. Aprobar vacaciones de Juan\n3. Actualizar documentación API",
    "intent": "list_tasks",
    "confidence": 0.95,
    "tokens_used": 145,
    "processing_time_ms": 234
  },
  "session_id": "sess_abc123",
  "timestamp": "2023-10-15T14:30:00Z"
}
```

**Respuestas de Error / Error Responses:**

| Código | Escenario | Ejemplo |
|--------|-----------|---------|
| 400 | Validación fallida | `{"error": "message is required"}` |
| 401 | Token inválido/expirado | `{"error": "Invalid token"}` |
| 403 | DPI detectó datos sensibles | `{"error": "Sensitive data detected", "type": "credit_card"}` |
| 429 | Rate limit excedido | `{"error": "Rate limit exceeded", "retry_after": 60}` |
| 500 | Error interno | `{"error": "Internal server error", "trace_id": "xyz789"}` |

---

### 2.2 Integraciones / Integrations

#### GET /integrations

Listar integraciones activas del usuario.

```http
GET /integrations
Authorization: Bearer {token}
```

**Respuesta / Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "int_001",
      "provider": "whatsapp",
      "status": "active",
      "connected_at": "2023-10-01T10:00:00Z",
      "last_sync": "2023-10-15T14:00:00Z"
    },
    {
      "id": "int_002",
      "provider": "google_classroom",
      "status": "active",
      "connected_at": "2023-10-05T08:30:00Z",
      "last_sync": "2023-10-15T12:00:00Z"
    },
    {
      "id": "int_003",
      "provider": "trello",
      "status": "warning",
      "warning_message": "Token expira en 7 días",
      "connected_at": "2023-09-15T16:00:00Z",
      "last_sync": "2023-10-14T09:00:00Z"
    }
  ]
}
```

#### POST /integrations/connect

Conectar nueva integración.

```http
POST /integrations/connect
Content-Type: application/json
Authorization: Bearer {token}

{
  "provider": "trello",
  "credentials": {
    "api_key": "YOUR_API_KEY",
    "token": "YOUR_TOKEN"
  },
  "options": {
    "sync_direction": "bidirectional",
    "default_board": "Proyectos 2024"
  }
}
```

#### DELETE /integrations/{integration_id}

Desconectar integración.

```http
DELETE /integrations/int_001
Authorization: Bearer {token}
```

---

### 2.3 Tareas / Tasks

#### GET /tasks

Listar tareas del usuario.

```http
GET /tasks?status=pending&limit=10&offset=0
Authorization: Bearer {token}
```

**Query Parameters:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `status` | string | all | pending, completed, overdue |
| `limit` | integer | 20 | Máximo de resultados |
| `offset` | integer | 0 | Paginación |
| `due_date_from` | date | - | Filtrar por fecha mínima |
| `due_date_to` | date | - | Filtrar por fecha máxima |

**Respuesta / Response:**
```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "id": "task_001",
        "title": "Revisar informe Q3",
        "description": "Revisar y aprobar el informe financiero del Q3",
        "status": "pending",
        "priority": "high",
        "due_date": "2023-10-16T17:00:00Z",
        "source": "trello",
        "source_id": "card_xyz123",
        "created_at": "2023-10-10T09:00:00Z"
      },
      {
        "id": "task_002",
        "title": "Entregar tarea OWASP Top 10",
        "description": "Análisis de vulnerabilidades",
        "status": "pending",
        "priority": "medium",
        "due_date": "2023-10-25T23:59:00Z",
        "source": "google_classroom",
        "source_id": "assignment_abc456",
        "created_at": "2023-10-01T08:00:00Z"
      }
    ],
    "pagination": {
      "total": 15,
      "limit": 10,
      "offset": 0,
      "has_more": true
    }
  }
}
```

#### POST /tasks

Crear nueva tarea.

```http
POST /tasks
Content-Type: application/json
Authorization: Bearer {token}

{
  "title": "Reunión con cliente",
  "description": "Presentar propuesta comercial",
  "due_date": "2023-10-20T15:00:00Z",
  "priority": "high",
  "source": "manual",
  "metadata": {
    "client_name": "Empresa XYZ",
    "meeting_link": "https://zoom.us/j/123456789"
  }
}
```

#### PATCH /tasks/{task_id}

Actualizar tarea.

```http
PATCH /tasks/task_001
Content-Type: application/json
Authorization: Bearer {token}

{
  "status": "completed",
  "completed_at": "2023-10-15T14:30:00Z"
}
```

#### DELETE /tasks/{task_id}

Eliminar tarea.

```http
DELETE /tasks/task_001
Authorization: Bearer {token}
```

---

### 2.4 Memoria y Contexto / Memory & Context

#### GET /memory/session/{session_id}

Obtener contexto de sesión.

```http
GET /memory/session/sess_abc123
Authorization: Bearer {token}
```

**Respuesta / Response:**
```json
{
  "status": "success",
  "data": {
    "session_id": "sess_abc123",
    "created_at": "2023-10-15T10:00:00Z",
    "last_activity": "2023-10-15T14:30:00Z",
    "message_count": 25,
    "topics": ["soporte técnico", "tareas", "reuniones"],
    "preferences": {
      "language": "es",
      "timezone": "America/Mexico_City"
    }
  }
}
```

#### DELETE /memory/session/{session_id}

Eliminar sesión (derecho al olvido).

```http
DELETE /memory/session/sess_abc123
Authorization: Bearer {token}
```

#### POST /memory/clear

Eliminar toda la memoria del usuario.

```http
POST /memory/clear
Content-Type: application/json
Authorization: Bearer {token}

{
  "confirm": true,
  "reason": "GDPR request"
}
```

---

### 2.5 Métricas y Reportes / Metrics & Reports

#### GET /metrics/productivity

Obtener reporte de productividad.

```http
GET /metrics/productivity?period=week&start_date=2023-10-09
Authorization: Bearer {token}
```

**Respuesta / Response:**
```json
{
  "status": "success",
  "data": {
    "period": "week",
    "start_date": "2023-10-09",
    "end_date": "2023-10-15",
    "metrics": {
      "tasks_completed": 12,
      "tasks_pending": 5,
      "completion_rate": 0.71,
      "avg_response_time_ms": 245,
      "messages_exchanged": 87,
      "automation_savings_minutes": 145
    },
    "top_intents": [
      {"intent": "list_tasks", "count": 25},
      {"intent": "create_task", "count": 18},
      {"intent": "question", "count": 15}
    ]
  }
}
```

---

## 3. Webhooks

### 3.1 Configurar Webhook

```http
POST /webhooks
Content-Type: application/json
Authorization: Bearer {token}

{
  "url": "https://tu-sistema.com/webhooks/helios",
  "events": ["task.created", "task.completed", "alert.triggered"],
  "secret": "tu_webhook_secret"
}
```

### 3.2 Eventos Disponibles / Available Events

| Evento | Payload Ejemplo |
|--------|-----------------|
| `task.created` | `{"event": "task.created", "task_id": "task_001", ...}` |
| `task.completed` | `{"event": "task.completed", "task_id": "task_001", ...}` |
| `task.overdue` | `{"event": "task.overdue", "task_id": "task_001", ...}` |
| `alert.triggered` | `{"event": "alert.triggered", "severity": "HIGH", ...}` |
| `security.dpi_blocked` | `{"event": "security.dpi_blocked", "type": "credit_card", ...}` |

### 3.3 Verificar Firma / Verify Signature

Helios firma los webhooks con HMAC-SHA256:

```python
import hmac
import hashlib

def verify_signature(payload, signature, secret):
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Header recibido: `X-Helios-Signature: sha256=abc123...`

---

## 4. Rate Limits y Cuotas
## 4. Rate Limits & Quotas

| Plan | Requests/minuto | Requests/día | Concurrent Sessions |
|------|-----------------|--------------|---------------------|
| Free | 10 | 1,000 | 3 |
| Pro | 60 | 50,000 | 20 |
| Enterprise | 300 | Ilimitado | Ilimitado |

### Headers de Rate Limit

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1697380800
```

---

## 5. Códigos de Error
## 5. Error Codes

| Código | Nombre | Descripción |
|--------|--------|-------------|
| `ERR_001` | VALIDATION_ERROR | Datos de entrada inválidos |
| `ERR_002` | AUTH_FAILED | Autenticación fallida |
| `ERR_003` | PERMISSION_DENIED | Permisos insuficientes |
| `ERR_004` | DPI_BLOCKED | Datos sensibles detectados |
| `ERR_005` | RATE_LIMIT_EXCEEDED | Límite de tasa excedido |
| `ERR_006` | INTEGRATION_ERROR | Error con proveedor externo |
| `ERR_007` | NOT_FOUND | Recurso no encontrado |
| `ERR_008` | INTERNAL_ERROR | Error interno del servidor |

---

## 6. SDKs y Librerías / SDKs & Libraries

### Python

```bash
pip install helios-sdk
```

```python
from helios import HeliosClient

client = HeliosClient(api_key="your_api_key")

# Enviar mensaje
response = client.chat.send("¿Qué tareas tengo pendientes?")
print(response.data.response)

# Listar tareas
tasks = client.tasks.list(status="pending")
for task in tasks.data.tasks:
    print(f"- {task.title}")
```

### JavaScript/Node.js

```bash
npm install @helios/sdk
```

```javascript
const { HeliosClient } = require('@helios/sdk');

const client = new HeliosClient({ apiKey: 'your_api_key' });

// Enviar mensaje
const response = await client.chat.send('¿Qué tareas tengo pendientes?');
console.log(response.data.response);
```

---

*Documentación completa disponible en: https://docs.helios-enterprise.com/api*
*Full documentation available at: https://docs.helios-enterprise.com/api*
