"""
Tests for Master Orchestrator Agent
"""

import pytest
import asyncio
from ai_engine.agents.master_orchestrator import MasterOrchestrator, TaskType, OrchestrationError


@pytest.fixture
def orchestrator():
    """Create a fresh orchestrator instance for each test."""
    return MasterOrchestrator()


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# TESTS DE CLASIFICACIÓN DE TAREAS (8+ casos de prueba)
# ============================================================================

class TestTaskClassification:
    """Tests for the classify_task method."""

    @pytest.mark.asyncio
    async def test_classify_pc_control_shutdown(self, orchestrator):
        """Test classification of PC control - shutdown requests."""
        result = await orchestrator.classify_task("Apaga el PC ahora")
        assert result["success"] is True
        assert result["task_type"] == TaskType.PC_CONTROL
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_pc_control_restart(self, orchestrator):
        """Test classification of PC control - restart requests."""
        result = await orchestrator.classify_task("Reinicia el sistema en 60 segundos")
        assert result["success"] is True
        assert result["task_type"] == TaskType.PC_CONTROL
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_pc_control_open_app(self, orchestrator):
        """Test classification of PC control - open application requests."""
        result = await orchestrator.classify_task("Abre Chrome por favor")
        assert result["success"] is True
        assert result["task_type"] == TaskType.PC_CONTROL
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_pentest_scan(self, orchestrator):
        """Test classification of pentest - scanning requests."""
        result = await orchestrator.classify_task("Escanea la red en busca de vulnerabilidades")
        assert result["success"] is True
        assert result["task_type"] == TaskType.PENTEST
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_pentest_nmap(self, orchestrator):
        """Test classification of pentest - nmap requests."""
        result = await orchestrator.classify_task("Ejecuta nmap para enumerar puertos")
        assert result["success"] is True
        assert result["task_type"] == TaskType.PENTEST
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_visual_capture(self, orchestrator):
        """Test classification of visual - screen capture requests."""
        result = await orchestrator.classify_task("Captura la pantalla del segundo monitor")
        assert result["success"] is True
        assert result["task_type"] == TaskType.VISUAL
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_visual_ocr(self, orchestrator):
        """Test classification of visual - OCR requests."""
        result = await orchestrator.classify_task("Haz OCR y lee el texto de esta imagen")
        assert result["success"] is True
        assert result["task_type"] == TaskType.VISUAL
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_security_virus(self, orchestrator):
        """Test classification of security - virus scan requests."""
        result = await orchestrator.classify_task("Analiza este archivo en busca de virus")
        assert result["success"] is True
        assert result["task_type"] == TaskType.SECURITY
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_security_prompt_injection(self, orchestrator):
        """Test classification of security - prompt injection detection."""
        result = await orchestrator.classify_task("Verifica si hay inyección de prompt en este email")
        assert result["success"] is True
        assert result["task_type"] == TaskType.SECURITY
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_classify_unknown(self, orchestrator):
        """Test classification of unknown/unrecognized requests."""
        result = await orchestrator.classify_task("Hola, ¿cómo estás?")
        assert result["success"] is True
        assert result["task_type"] == TaskType.UNKNOWN
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_classify_mixed_keywords_priority(self, orchestrator):
        """Test classification when multiple categories match - priority tie-breaker."""
        # This request has keywords from multiple categories
        result = await orchestrator.classify_task("Abre el archivo y escanea el sistema")
        assert result["success"] is True
        # Should resolve to one category based on priority
        assert result["task_type"] in [TaskType.PC_CONTROL, TaskType.SECURITY, TaskType.PENTEST, TaskType.VISUAL]


# ============================================================================
# TESTS DE DELEGACIÓN A AGENTES
# ============================================================================

class TestAgentDelegation:
    """Tests for the delegate_to_agent method."""

    @pytest.mark.asyncio
    async def test_delegate_to_pc_controller(self, orchestrator):
        """Test successful delegation to PC controller agent."""
        task_details = {
            "operation": "get_system_info",
            "target": "local_system",
            "parameters": {}
        }
        result = await orchestrator.delegate_to_agent(TaskType.PC_CONTROL, task_details)
        assert result is not None
        assert "success" in result or "status" in result

    @pytest.mark.asyncio
    async def test_delegate_to_pentest_agent(self, orchestrator):
        """Test successful delegation to pentest agent."""
        task_details = {
            "operation": "reconnaissance",
            "target": "localhost",
            "parameters": {}
        }
        result = await orchestrator.delegate_to_agent(TaskType.PENTEST, task_details)
        assert result is not None
        assert "status" in result

    @pytest.mark.asyncio
    async def test_delegate_to_visual_agent(self, orchestrator):
        """Test successful delegation to visual agent."""
        task_details = {
            "operation": "capture_screen",
            "target": "screen",
            "parameters": {"monitor_index": 0}
        }
        result = await orchestrator.delegate_to_agent(TaskType.VISUAL, task_details)
        assert result is not None
        # VisualAgent returns success/message/data/error format
        assert "success" in result or "status" in result

    @pytest.mark.asyncio
    async def test_delegate_to_security_agent(self, orchestrator):
        """Test successful delegation to security agent."""
        task_details = {
            "operation": "scan_file",
            "target": "test.exe",
            "parameters": {}
        }
        result = await orchestrator.delegate_to_agent(TaskType.SECURITY, task_details)
        assert result is not None
        # SecurityShield returns success/message/data/error format
        assert "success" in result or "status" in result

    @pytest.mark.asyncio
    async def test_delegate_to_nonexistent_agent(self, orchestrator):
        """Test delegation to a non-existent agent type raises error."""
        # Create a custom TaskType that doesn't exist
        task_details = {"operation": "test"}
        
        # Temporarily unregister all agents to test error handling
        original_agents = orchestrator._agents.copy()
        orchestrator._agents.clear()
        
        with pytest.raises(OrchestrationError):
            await orchestrator.delegate_to_agent(TaskType.PC_CONTROL, task_details)
        
        # Restore agents
        orchestrator._agents = original_agents


# ============================================================================
# TESTS DE MANEJO DE ERRORES
# ============================================================================

class TestErrorHandling:
    """Tests for error handling in the orchestrator."""

    @pytest.mark.asyncio
    async def test_process_request_with_invalid_input(self, orchestrator):
        """Test processing request with invalid/empty input."""
        result = await orchestrator.process_user_request("")
        assert result["success"] is False
        assert result["error"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_process_request_unauthorized_target(self, orchestrator):
        """Test processing request with unauthorized target."""
        context = {"target": "/etc/shadow"}  # Protected path
        result = await orchestrator.process_user_request("Analiza este archivo", context=context)
        # Should either be denied or fail authorization
        assert result["success"] is False or "unauthorized" in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_orchestration_error_recovery(self, orchestrator):
        """Test that orchestration errors trigger recovery mechanisms."""
        # Test the _attempt_recovery method directly
        error = Exception("Simulated failure")
        task_details = {"operation": "shutdown"}
        
        result = await orchestrator._attempt_recovery(TaskType.PC_CONTROL, task_details, error)
        assert result is not None
        assert result["success"] is False
        assert "recovery_mode" in result.get("data", {})


# ============================================================================
# TESTS DE FLUJO COMPLETO
# ============================================================================

class TestFullWorkflow:
    """Tests for the complete process_user_request flow."""

    @pytest.mark.asyncio
    async def test_full_workflow_pc_shutdown(self, orchestrator):
        """Test complete workflow for PC shutdown request."""
        result = await orchestrator.process_user_request(
            "Apaga el PC en 30 segundos",
            context={"target": "local_system"}
        )
        assert result is not None
        assert "success" in result
        assert "message" in result
        assert "metadata" in result
        assert result["metadata"]["task_type"] == "pc_control"

    @pytest.mark.asyncio
    async def test_full_workflow_vulnerability_scan(self, orchestrator):
        """Test complete workflow for vulnerability scan request."""
        result = await orchestrator.process_user_request(
            "Escanea el localhost en busca de vulnerabilidades",
            context={"target": "localhost"}
        )
        assert result is not None
        assert result["metadata"]["task_type"] == "pentest"

    @pytest.mark.asyncio
    async def test_full_workflow_screen_capture(self, orchestrator):
        """Test complete workflow for screen capture request."""
        result = await orchestrator.process_user_request(
            "Captura la pantalla del monitor secundario",
            context={"target": "localhost"}  # Use authorized target
        )
        assert result is not None
        assert result["metadata"]["task_type"] == "visual"

    @pytest.mark.asyncio
    async def test_full_workflow_virus_scan(self, orchestrator):
        """Test complete workflow for virus scan request."""
        result = await orchestrator.process_user_request(
            "Analiza este archivo exe en busca de malware",
            context={"target": "files"}
        )
        assert result is not None
        assert result["metadata"]["task_type"] == "security"

    @pytest.mark.asyncio
    async def test_full_workflow_with_processing_time(self, orchestrator):
        """Test that full workflow includes processing time metadata."""
        result = await orchestrator.process_user_request(
            "Reinicia el sistema",
            context={"target": "local_system"}
        )
        assert "metadata" in result
        assert "processing_time_ms" in result["metadata"]
        assert result["metadata"]["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_full_workflow_unknown_request(self, orchestrator):
        """Test complete workflow for unrecognized request."""
        result = await orchestrator.process_user_request(
            "¿Cuál es el clima hoy?",
            context={}
        )
        assert result["success"] is False
        assert result["error"] == "unknown_task_type"
        assert "supported_types" in result.get("data", {})


# ============================================================================
# TESTS DE UTILIDADES Y ESTADO
# ============================================================================

class TestUtilityMethods:
    """Tests for utility methods in the orchestrator."""

    def test_get_registered_agents(self, orchestrator):
        """Test getting list of registered agents."""
        agents = orchestrator.get_registered_agents()
        assert isinstance(agents, dict)
        assert "pc_control" in agents
        assert "pentest" in agents
        assert "visual" in agents
        assert "security" in agents

    def test_get_agent_health_status(self, orchestrator):
        """Test getting health status of all agents."""
        health = orchestrator.get_agent_health_status()
        assert isinstance(health, dict)
        # All agents should be active initially
        assert all(status is True for status in health.values())

    def test_extract_operation_pc_control(self, orchestrator):
        """Test operation extraction for PC control requests."""
        operation = orchestrator._extract_operation("Apaga el PC ahora")
        assert operation == "shutdown"
        
        operation = orchestrator._extract_operation("Reinicia el sistema")
        assert operation == "restart"
        
        operation = orchestrator._extract_operation("Abre Chrome")
        assert operation == "open_app"

    def test_extract_operation_pentest(self, orchestrator):
        """Test operation extraction for pentest requests."""
        operation = orchestrator._extract_operation("Escanea la red")
        assert operation == "vulnerability_scan"
        
        # nmap with puertos triggers reconnaissance
        operation = orchestrator._extract_operation("Usa nmap para enumerar puertos")
        assert operation == "reconnaissance"

    def test_extract_parameters_delay(self, orchestrator):
        """Test parameter extraction for delay values."""
        params = orchestrator._extract_parameters(
            "Apaga el PC en 60 segundos",
            TaskType.PC_CONTROL
        )
        assert "delay_seconds" in params
        assert params["delay_seconds"] == 60

    def test_extract_parameters_ip_address(self, orchestrator):
        """Test parameter extraction for IP addresses."""
        params = orchestrator._extract_parameters(
            "Escanea 192.168.1.100 en busca de puertos abiertos",
            TaskType.PENTEST
        )
        assert "target_ip" in params
        assert params["target_ip"] == "192.168.1.100"


# ============================================================================
# TESTS DE BROADCAST
# ============================================================================

class TestBroadcast:
    """Tests for broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_to_all_agents(self, orchestrator):
        """Test broadcasting a task to all agents."""
        task = {"operation": "test", "target": "localhost"}
        results = await orchestrator.broadcast_task(task)
        
        assert isinstance(results, dict)
        assert len(results) == 4  # One for each agent type
        
    @pytest.mark.asyncio
    async def test_broadcast_with_exclusions(self, orchestrator):
        """Test broadcasting with excluded agent types."""
        task = {"operation": "test", "target": "localhost"}
        exclude = [TaskType.VISUAL, TaskType.PENTEST]
        results = await orchestrator.broadcast_task(task, exclude_types=exclude)
        
        assert isinstance(results, dict)
        assert len(results) == 2  # Only PC_CONTROL and SECURITY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
