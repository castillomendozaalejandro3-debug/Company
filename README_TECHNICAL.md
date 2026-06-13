# Helios AI - README Técnico para Desarrolladores

## Descripción General

Helios AI es un sistema de automatización inteligente con arquitectura híbrida Rust/Python, diseñado para ser auto-reparable, seguro y escalable.

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                     HELIOS AI SYSTEM                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐     gRPC      ┌─────────────────────────┐  │
│  │ Rust Core   │◄─────────────►│   Python KernelDaemon   │  │
│  │ (Actor Lib) │               │  ┌───────────────────┐  │  │
│  └─────────────┘               │  │   Actor System    │  │  │
│                                │  ├───────────────────┤  │  │
│                                │  │  Worker Manager   │  │  │
│                                │  ├───────────────────┤  │  │
│                                │  │ Self-Healing Sys  │  │  │
│                                │  ├───────────────────┤  │  │
│                                │  │  DPI Validator    │  │  │
│                                │  └───────────────────┘  │  │
│                                └─────────────────────────┘  │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │Office Agent │  │ Email Agent │  │  GUI Agent  │ ...      │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Estructura de Directorios

```
/workspace/
├── ai_engine/
│   ├── core/
│   │   ├── kernel_daemon.py      # Núcleo principal del daemon
│   │   ├── actor_system.py       # Sistema de actores estilo Erlang/OTP
│   │   ├── worker_manager.py     # Gestor de ciclo de vida de workers
│   │   ├── self_healing.py       # Sistema de auto-reparación
│   │   ├── git_rollback.py       # Rollback atómico con Git
│   │   ├── sandbox_tdd.py        # Sandbox para pruebas TDD
│   │   └── dpi_validator.py      # Validador DPI semántico
│   └── agents/
│       ├── office_agent.py       # Agente Word/Excel/PowerPoint
│       └── email_agent.py        # Agente de correo electrónico
├── core/                          # Núcleo Rust (gRPC server)
├── scripts/
│   ├── master_setup.bat/sh       # Script maestro de configuración
│   ├── start_daemon.bat          # Inicio del daemon
│   ├── stop_daemon.bat           # Parada del daemon
│   ├── generate_certs.py         # Generador certificados X.509
│   └── backup_audit_db.bat       # Backup cifrado de auditoría
├── config/
│   ├── workspace.json            # Configuración del workspace
│   └── allowed_domains.json      # Dominios autorizados DPI
├── docker-compose.prod.yml        # Docker Compose producción
└── README_TECHNICAL.md           # Este archivo
```

## Componentes Principales

### 1. Kernel Daemon (`ai_engine/core/kernel_daemon.py`)

El núcleo inmutable del sistema que:
- Gestiona el servidor gRPC en puerto 50051
- Coordina el Actor System y Worker Manager
- Implementa health checks continuos

**Uso:**
```python
from ai_engine.core.kernel_daemon import KernelDaemon

daemon = KernelDaemon(host="0.0.0.0", port=50051)
await daemon.start()
```

### 2. Actor System (`ai_engine/core/actor_system.py`)

Sistema de concurrencia basado en actores:
- Aislamiento de fallos por diseño
- Mensajería asíncrona entre componentes
- Estrategias de supervisión jerárquicas

**Tipos de Actores:**
- `Actor`: Clase base
- `WorkerActor`: Para workers especializados
- `SupervisorActor`: Gestión de hijos y recuperación

### 3. Worker Manager (`ai_engine/core/worker_manager.py`)

Gestiona el ciclo de vida de workers:
- Creación/destrucción dinámica
- Monitor de salud en segundo plano
- Auto-reinicio ante timeouts

**Tipos de Workers:**
```python
WorkerType.OFFICE    # Automatización Office
WorkerType.EMAIL     # Gestión de correo
WorkerType.GUI       # Automatización GUI
WorkerType.WEB       # Scraping web
WorkerType.API       # Integraciones API
WorkerType.PENTEST   # Testing seguridad
```

### 4. Self-Healing System (`ai_engine/core/self_healing.py`)

Detección y recuperación automática:
- Health checks continuos (CPU, RAM, Disco, Servicios)
- Estrategias de recuperación configurables
- Escalado automático a administradores

**Estados de Salud:**
- `HEALTHY`: Todo operativo
- `DEGRADED`: Problemas menores
- `CRITICAL`: Requiere intervención
- `FAILED`: Componente caído

### 5. Git Rollback (`ai_engine/core/git_rollback.py`)

Rollback atómico de versiones:
- Backups automáticos antes de rollback
- Tags de recuperación
- Integración con auditoría

**Uso:**
```python
from ai_engine.core.git_rollback import GitRollback

rollback = GitRollback()
success = await rollback.rollback_last_commit(preserve_changes=False)
```

### 6. Sandbox TDD (`ai_engine/core/sandbox_tdd.py`)

Entorno aislado para pruebas:
- Ejecución segura de código no confiado
- Timeout y límites de recursos
- Ciclo completo Red-Green-Refactor

### 7. DPI Validator (`ai_engine/core/dpi_validator.py`)

Validación semántica de tráfico:
- URLs, emails, IPs, payloads
- Patrones regex configurables
- Detección de inyecciones

**Niveles de Amenaza:**
- `NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`

## Scripts de Despliegue

### Master Setup (Windows/Linux)

```bash
# Windows
scripts\master_setup.bat

# Linux/Mac
./scripts/master_setup.sh
```

**Pasos que ejecuta:**
1. Verifica Python 3.9+
2. Crea entorno virtual
3. Instala dependencias
4. Verifica/instala Rust
5. Compila núcleo Rust
6. Genera stubs gRPC
7. Inicializa SQLite

### Start/Stop Daemon

```bash
# Iniciar
scripts\start_daemon.bat

# Detener
scripts\stop_daemon.bat
```

### Generar Certificados mTLS

```bash
python scripts/generate_certs.py
```

Genera CA raíz + certificados para Kernel y Workers (en memoria).

### Backup Audit DB

```bash
scripts\backup_audit_db.bat
```

Crea backup cifrado AES-256 con hash SHA-256 de integridad.

## Configuración

### workspace.json

```json
{
  "kernel": {
    "port": 50051,
    "max_workers": 100
  },
  "security": {
    "enable_mtls": true,
    "audit_retention_days": 90
  },
  "self_healing": {
    "enabled": true,
    "auto_recovery": true
  }
}
```

### allowed_domains.json

Configura dominios permitidos y patrones bloqueados para DPI.

## Docker Producción

```bash
docker-compose -f docker-compose.prod.yml up -d
```

**Servicios incluidos:**
- `rust-core`: Núcleo Rust gRPC
- `kernel-daemon`: Daemon Python
- `dashboard`: UI Next.js
- `prometheus`: Métricas
- `grafana`: Visualización

## Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `EMAIL_USER` | Usuario SMTP | - |
| `EMAIL_PASSWORD` | Contraseña SMTP | - |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram | - |
| `SLACK_WEBHOOK_URL` | Webhook Slack | - |
| `GRAFANA_ADMIN_PASSWORD` | Password admin Grafana | `admin123` |

## Desarrollo

### Añadir un nuevo Agente

1. Heredar de `BaseAgent` en `ai_engine/agents/`
2. Implementar `initialize()`, `execute_task()`, `shutdown()`
3. Registrar capacidades en `self.capabilities`
4. Añadir tests en `tests/agents/`

### Añadir regla DPI

Editar `config/allowed_domains.json`:
```json
{
  "blocked_patterns": ["nuevo_patron"],
  "blocked_keywords": ["keyword_peligrosa"]
}
```

## Seguridad

- **mTLS**: Certificados efímeros X.509 para comunicación interna
- **Audit Log**: Todos los eventos registrados en SQLite cifrado
- **Sandbox**: Ejecución aislada de código no confiado
- **Git Rollback**: Recuperación ante cambios problemáticos

## Monitoreo

- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3001`
- **Kernel gRPC**: Puerto 50051
- **Dashboard UI**: Puerto 3000

## Troubleshooting

### El daemon no inicia
1. Verificar puerto 50051 libre: `netstat -ano | findstr :50051`
2. Revisar logs: `logs/kernel_daemon.log`
3. Ejecutar en modo debug: `python ai_engine/core/kernel_daemon.py`

### Tests fallan en Sandbox
1. Verificar dependencias instaladas
2. Aumentar timeout en `run_test(timeout=60)`
3. Revisar permisos de directorio temporal

### Rollback falla
1. Verificar repositorio Git válido
2. Confirmar commits existen: `git log --oneline`
3. Usar `force=True` si hay cambios no commiteados

## Licencia

Propietario - Helios AI System
