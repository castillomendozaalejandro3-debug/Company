# Helios Multi-Agent Architecture

## Overview

Helios implements a **multi-agent architecture** where specialized agents handle different domains of functionality, all coordinated through a central **Master Orchestrator**. This design enables modular scalability, clear separation of concerns, and robust security controls.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      User Interface Layer                        │
│                    (CLI / GUI / API Gateway)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Master Orchestrator Agent                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  • Task Routing & Delegation                               │  │
│  │  • Authorization Validation                                │  │
│  │  • Inter-Agent Communication (gRPC)                        │  │
│  │  • Health Monitoring                                       │  │
│  │  • Action Logging & Audit                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │              │              │              │
         │ gRPC         │ gRPC         │ gRPC         │ gRPC
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│    PC       │ │   Pentest   │ │   Visual    │ │  Security   │
│ Controller  │ │   Agent     │ │   Agent     │ │   Shield    │
│   Agent     │ │             │ │             │ │   Agent     │
├─────────────┤ ├─────────────┤ ├─────────────┤ ├─────────────┤
│ • Shutdown  │ │ • Recon     │ │ • OCR       │ │ • Antivirus │
│ • Restart   │ │ • Scanning  │ │ • Screen    │ │ • Threat    │
│ • Apps      │ │ • Exploits  │ │   Control   │ │   Detection │
│ • Commands  │ │ • Reports   │ │ • Monitor   │ │ • Rollback  │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

## Agent Descriptions

### 1. Master Orchestrator (`master_orchestrator.py`)

The central coordination point for all agent operations.

**Responsibilities:**
- Receive and analyze incoming tasks
- Determine appropriate agent based on task type
- Delegate tasks via gRPC channels
- Aggregate results from specialized agents
- Maintain action logs for compliance
- Monitor agent health status

**Task Routing Logic:**
| Keywords | Routed To |
|----------|-----------|
| apagar, reiniciar, abrir, app | PC Controller |
| scan, vulnerability, exploit, pentest, owasp | Pentest Agent |
| ocr, screen, visual, monitor, capture | Visual Agent |
| antivirus, threat, malware, shield, protect | Security Shield |

**Communication Protocol:** All inter-agent communication occurs via **gRPC** for:
- Low-latency task delegation
- Strong typing with Protocol Buffers
- Bidirectional streaming support
- Built-in authentication and encryption

### 2. PC Controller Agent (`pc_controller.py`)

Handles system-level operations with built-in security validation.

**Capabilities:**
- Power management (shutdown, restart, sleep)
- Application control (open, close)
- Command execution with safety filters
- File operations with path restrictions

**Security Features:**
- Whitelist-based application control
- Dangerous command pattern blocking
- Protected directory access prevention
- Confirmation requirements for critical operations

### 3. Pentest Agent (`pentest_agent.py`)

Autonomous penetration testing and security assessment.

**Capabilities:**
- Dynamic reconnaissance (Nmap/Masscan integration)
- Vulnerability scanning (OWASP Top 10)
- Exploit orchestration (Metasploit integration)
- Automated report generation
- Compliance documentation (PTES, NIST)

**Authorization Model:**
- Explicit target authorization required
- Authorized targets maintained in whitelist
- Pattern-based domain/IP range matching
- Localhost always authorized for testing

**Pentesting Phases:**
1. **Reconnaissance**: Passive/active information gathering
2. **Scanning**: Vulnerability identification
3. **Exploitation**: Controlled exploit execution
4. **Post-Exploitation**: Access maintenance
5. **Reporting**: Documentation and recommendations

### 4. Visual Agent (`visual_agent.py`)

Screen control, OCR, and GUI automation optimized for secondary monitor operations.

**Capabilities:**
- Screen capture and analysis
- Optical Character Recognition (OCR)
- GUI element detection and interaction
- Multi-monitor management
- Visual workflow automation

**Use Cases:**
- Secondary monitor autonomous operation
- Context-aware screen reading
- GUI-based application control
- Visual data extraction

### 5. Security Shield Agent (`security_shield.py`)

Native antivirus and active threat protection.

**Capabilities:**
- Behavioral malware analysis
- Zero-day attack neutralization
- Instant system rollback
- AI prompt injection filtering
- Smart network isolation
- Credential auditing
- Real-time threat monitoring

**Threat Levels:**
- `NONE`: No active threats
- `LOW`: Minor anomalies detected
- `MEDIUM`: Suspicious activity identified
- `HIGH`: Active threat requiring attention
- `CRITICAL`: Immediate response required

**Protection Mechanisms:**
- Signature-based scanning
- Behavioral analysis
- Prompt injection detection
- Network containment
- System snapshots for rollback

## Base Agent Interface

All agents inherit from `BaseAgent` which defines the required interface:

```python
class BaseAgent(ABC):
    @abstractmethod
    async def execute_task(self, task: dict) -> dict:
        """Execute a given task and return results."""
        pass

    @abstractmethod
    async def check_authorization(self, target: str) -> bool:
        """Verify if an action is authorized."""
        pass

    @abstractmethod
    async def log_action(self, action: str, context: dict) -> None:
        """Record actions for audit and compliance."""
        pass
```

### PC Controller Agent Implementation Details

The `PCControllerAgent` extends the base interface with specific functionality:

**Custom Exceptions:**
- `SecurityValidationError`: Raised when security validation fails
- `ExecutionError`: Raised when command execution fails
- `AuthorizationError`: Raised when authorization check fails

**Core Methods:**
```python
async def shutdown_system(delay_seconds: int = 0) -> dict:
    """Shutdown system with security validation and critical process detection."""

async def restart_system(delay_seconds: int = 0) -> dict:
    """Restart system with security validation."""

async def open_application(app_name: str) -> dict:
    """Open application with OS-specific commands."""

async def execute_command(command: str, requires_confirmation: bool = True) -> dict:
    """Execute shell command with dangerous pattern detection."""

async def get_system_info() -> dict:
    """Retrieve CPU, RAM, disk, and platform information."""
```

**Response Structure:**
All methods return a standardized dictionary:
```python
{
    "success": bool,       # Whether operation succeeded
    "message": str,        # Human-readable description
    "data": Any,           # Operation-specific data
    "error": str | None    # Error message if failed
}
```

**Security Validation Process:**
1. Check for critical processes before destructive operations
2. Validate against dangerous command patterns
3. Require explicit confirmation for high-risk actions
4. Log all actions with timestamp, status, and context
5. Block access to sensitive system paths

**Logging Format:**
All actions are logged to `logs/pc_controller.log` with format:
```
[TIMESTAMP] [ACTION] [STATUS] [CONTEXT]
```

Example:
```
[2024-01-15T10:30:45.123456] [shutdown] [SUCCESS] {"command": "shutdown /s /t 60", "os_type": "windows", "simulated": true}
```

**OS Detection and Command Adaptation:**
The agent automatically detects the operating system and adjusts commands:

| Operation | Windows | macOS | Linux |
|-----------|---------|-------|-------|
| Shutdown | `shutdown /s /t <delay>` | `sudo shutdown -h +<min>` | `sudo shutdown -h +<min>` |
| Restart | `shutdown /r /t <delay>` | `sudo shutdown -r +<min>` | `sudo shutdown -r +<min>` |
| Open App | `start "" <app>` | `open -a <app>` | `xdg-open <app>` |
| List Processes | `tasklist /FO CSV` | `ps aux` | `ps aux` |
| CPU Info | `wmic cpu get...` | `nproc` | `nproc` |
| RAM Info | `wmic OS get...` | `free -h` | `free -h` |
| Disk Info | `wmic logicaldisk get...` | `df -h` | `df -h` |

## Communication Flow

### Standard Task Execution

1. **User submits task** → Master Orchestrator receives request
2. **Orchestrator analyzes** → Determines task type via keyword matching
3. **Authorization check** → Validates target permissions
4. **gRPC delegation** → Routes task to specialized agent
5. **Agent executes** → Performs operation with logging
6. **Result aggregation** → Orchestrator collects and formats response
7. **Response to user** → Returns unified result

### Cross-Agent Collaboration

For complex tasks requiring multiple agents:

1. Master Orchestrator identifies need for collaboration
2. Broadcasts task to relevant agents via gRPC
3. Collects partial results from each agent
4. Aggregates into comprehensive response
5. Maintains correlation IDs for audit trail

## Security Model

### Authorization Layers

1. **User Authentication**: Verify user identity
2. **Target Authorization**: Validate target permissions
3. **Operation Authorization**: Check operation allowed
4. **Context Validation**: Ensure safe execution context

### Audit Logging

All actions are logged with:
- Timestamp
- Agent ID and name
- Action description
- Context parameters
- Result status
- Threat level (for security operations)

### Isolation Boundaries

- Agents operate in isolated execution contexts
- gRPC channels encrypted with TLS
- Sensitive operations require explicit confirmation
- Protected system paths blocked by default

## Extension Points

### Adding New Agents

1. Create new agent class inheriting from `BaseAgent`
2. Implement required abstract methods
3. Register with Master Orchestrator:
   ```python
   orchestrator.register_agent(TaskType.NEW_TYPE, new_agent)
   ```
4. Define task routing keywords in `_determine_task_type()`

### Custom Task Types

Extend `TaskType` enum in `master_orchestrator.py`:
```python
class TaskType(Enum):
    PC_CONTROL = "pc_control"
    PENTEST = "pentest"
    VISUAL = "visual"
    SECURITY = "security"
    GENERAL = "general"
    # Add new types here
```

## Deployment Considerations

### gRPC Configuration

- Use mutual TLS for agent authentication
- Configure connection pooling for efficiency
- Set appropriate timeouts for long-running tasks
- Enable health checking for agent monitoring

### Scalability

- Agents can be deployed on separate processes or machines
- Load balancing possible for high-volume scenarios
- Message queues for asynchronous task processing
- Horizontal scaling of specific agent types

### Monitoring

- Health status available via `get_agent_health_status()`
- Action logs exportable for SIEM integration
- Metrics collection for performance analysis
- Alert integration for security events

## File Structure

```
ai_engine/
├── __init__.py
└── agents/
    ├── __init__.py
    ├── base_agent.py          # Abstract base class
    ├── master_orchestrator.py # Central coordinator
    ├── pc_controller.py       # System control agent
    ├── pentest_agent.py       # Security testing agent
    ├── visual_agent.py        # Screen/OCR agent
    └── security_shield.py     # Antivirus/threat agent
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024 | Initial multi-agent architecture implementation |
