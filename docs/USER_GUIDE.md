# Helios AI Kernel - Guía de Usuario
# Helios AI Kernel - User Guide

**Versión:** 1.0.0  
**Público Objetivo:** Usuarios finales, administradores y desarrolladores  
**Idioma:** Español / English (Bilingüe)

---

## 1. Introducción / Introduction

Helios es un asistente de IA empresarial que se integra con tus herramientas diarias (WhatsApp, Google Classroom, Trello, etc.) para automatizar tareas, responder consultas y gestionar información de forma segura.

Helios is an enterprise AI assistant that integrates with your daily tools (WhatsApp, Google Classroom, Trello, etc.) to automate tasks, answer queries, and manage information securely.

### ¿Qué puede hacer Helios? / What can Helios do?

- ✅ Responder preguntas frecuentes de soporte técnico
- ✅ Gestionar tareas y recordatorios en tu gestor de proyectos
- ✅ Sincronizar plazos académicos desde Google Classroom
- ✅ Enviar y recibir mensajes por WhatsApp e Instagram
- ✅ Proteger datos sensibles automáticamente (DLP)

---

## 2. Instalación y Configuración / Installation & Setup

### 2.1 Requisitos Previos / Prerequisites

- Python 3.11 o superior
- Docker y Docker Compose (recomendado)
- Cuenta en los servicios a integrar (Meta, Google, etc.)
- Variables de entorno configuradas (.env)

### 2.2 Instalación con Docker (Recomendado) / Docker Installation (Recommended)

```bash
# Clonar repositorio
git clone https://github.com/helios-ai/kernel.git
cd kernel

# Copiar archivo de ejemplo
cp .env.example .env

# Editar credenciales
nano .env

# Iniciar servicios
docker-compose up -d

# Verificar estado
docker-compose ps
```

### 2.3 Configuración de Variables de Entorno / Environment Variables Configuration

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Clave de API de OpenAI | `sk-...` |
| `TWILIO_SID` | Account SID de Twilio | `AC...` |
| `TWILIO_TOKEN` | Auth Token de Twilio | `...` |
| `GOOGLE_CREDENTIALS` | Ruta a JSON de Google | `/secrets/google.json` |
| `LOG_LEVEL` | Nivel de logging | `INFO`, `DEBUG`, `WARNING` |
| `DATABASE_URL` | URL de conexión a DB | `sqlite:///./helios.db` |

### 2.4 Instalación Manual (Desarrollo) / Manual Installation (Development)

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar tests
pytest

# Iniciar servidor
uvicorn ai_engine.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 3. Comandos Disponibles y Ejemplos / Available Commands & Examples

### 3.1 Vía API REST / Via REST API

#### Enviar Mensaje / Send Message

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuáles son mis tareas pendientes?",
    "channel": "whatsapp",
    "user_id": "usr_12345"
  }'
```

**Respuesta / Response:**
```json
{
  "status": "success",
  "response": "Tienes 3 tareas pendientes:\n1. Revisar informe Q3 (Vence: mañana)\n2. Aprobar vacaciones de Juan (Vence: viernes)\n3. Actualizar documentación API (Vence: lunes)",
  "session_id": "sess_abc123",
  "tokens_used": 145
}
```

#### Listar Integraciones Activas / List Active Integrations

```bash
curl -X GET "http://localhost:8000/api/v1/integrations" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 3.2 Vía CLI (Línea de Comandos) / Via CLI

```bash
# Iniciar interacción
helios chat --message "Recordatorio: reunión a las 3pm"

# Ver estado del sistema
helios status

# Exportar logs
helios logs --output ./logs/export.json --days 7
```

### 3.3 Casos de Uso Comunes / Common Use Cases

#### A. Soporte Técnico / IT Support

**Usuario:** "Mi correo no funciona"  
**Helios:** "Entiendo que tienes problemas con el correo. ¿Podrías indicarme:
1. ¿Qué mensaje de error ves?
2. ¿Desde qué dispositivo intentas acceder?
3. ¿Es la primera vez que ocurre?"

#### B. Gestión de Tareas / Task Management

**Usuario:** "Crea una tarea para revisar el presupuesto del proyecto X antes del viernes"  
**Helios:** "✅ Tarea creada en Trello:
- **Título:** Revisar presupuesto Proyecto X
- **Fecha límite:** Viernes, 17:00
- **Prioridad:** Alta
- **Asignado:** Tú
¿Deseas agregar algún colaborador?"

#### C. Consulta Académica / Academic Query

**Usuario:** "¿Cuándo vence la próxima tarea de Seguridad Informática?"  
**Helios:** "La próxima tarea de Seguridad Informática es:
- **Título:** Análisis de vulnerabilidades OWASP Top 10
- **Fecha de entrega:** 25 de Octubre, 23:59
- **Peso:** 20% de la calificación final
- **Estado:** No entregado"

---

## 4. Integración con Sistemas Existentes / Integration with Existing Systems

### 4.1 Google Workspace / Google Classroom

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear nuevo proyecto
3. Habilitar APIs: Classroom API, Calendar API
4. Crear Service Account y descargar JSON
5. Colocar JSON en `/secrets/google-classroom.json`
6. En Helios: `helios integrate google --credentials /secrets/google-classroom.json`

### 4.2 Meta (WhatsApp/Instagram)

1. Ir a [Meta Developers](https://developers.facebook.com/)
2. Crear App tipo "Business"
3. Agregar productos: WhatsApp, Instagram
4. Obtener tokens de acceso
5. Configurar webhooks apuntando a `https://tu-helios.com/webhooks/meta`
6. En Helios: `helios integrate meta --token YOUR_TOKEN`

### 4.3 Gestores de Tareas (Trello/Asana/Monday)

```bash
# Trello
helios integrate trello --api-key YOUR_KEY --token YOUR_TOKEN

# Asana
helios integrate asana --pat YOUR_PAT

# Monday.com
helios integrate monday --api-key YOUR_KEY
```

---

## 5. Troubleshooting / Solución de Problemas

### 5.1 Errores Comunes / Common Errors

#### Error: "Invalid API Key"

**Causa:** Credencial incorrecta o expirada  
**Solución:**
```bash
# Verificar variable de entorno
echo $OPENAI_API_KEY

# Regenerar token en portal del proveedor
# Actualizar .env y reiniciar
docker-compose restart
```

#### Error: "Rate Limit Exceeded"

**Causa:** Demasiadas solicitudes en poco tiempo  
**Solución:**
- Esperar 60 segundos antes de reintentar
- Implementar backoff exponencial en tu código
- Contactar soporte para aumentar quota si es necesario

#### Error: "DPI Validation Failed"

**Causa:** El mensaje contiene datos sensibles (tarjeta de crédito, SSN, etc.)  
**Solución:**
- No enviar datos sensibles por chat
- Usar canales seguros para información crítica
- Contactar al administrador si es falso positivo

### 5.2 Comandos de Diagnóstico / Diagnostic Commands

```bash
# Ver logs en tiempo real
docker-compose logs -f helios-api

# Ver métricas del sistema
curl http://localhost:8000/metrics

# Health check
curl http://localhost:8000/health

# Test de conectividad externa
helios diagnose --external-apis
```

### 5.3 Contactar Soporte / Contact Support

Si los pasos anteriores no resuelven el problema:

1. Recopilar logs: `helios logs --output support-bundle.tar.gz`
2. Documentar pasos para reproducir el error
3. Enviar a: support@helios-enterprise.com
4. Incluir ID de sesión y timestamp del error

---

## 6. Preguntas Frecuentes / FAQ

### ¿Es seguro enviar información confidencial a Helios?

Helios incluye protección DLP (Data Loss Prevention) que detecta y bloquea automáticamente el envío de datos sensibles como números de tarjetas de crédito, contraseñas o información personal identificable (PII). Sin embargo, recomendamos NO enviar información altamente sensible por chat.

### ¿Puedo usar Helios offline?

No. Helios requiere conexión a internet para comunicarse con los proveedores de LLM y APIs externas.

### ¿Cómo elimino mis datos de Helios?

Puedes solicitar la eliminación completa de tus datos ejecutando:
```bash
helios delete-data --user-id YOUR_USER_ID --confirm
```
Esto eliminará historial de chats, preferencias y caché asociado.

### ¿Helios funciona en mi idioma?

Sí, Helios soporta múltiples idiomas incluyendo español, inglés, francés, alemán, portugués y más. El idioma se detecta automáticamente según tu mensaje.

---

*Para más información, visitar: https://docs.helios-enterprise.com*
*For more information, visit: https://docs.helios-enterprise.com*
