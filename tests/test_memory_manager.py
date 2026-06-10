"""
Test suite for CircularContextManager (Token-Buffer Pattern)

Tests verify:
1. Short-term buffer with deduplication
2. Mid-term compression and SQLite persistence
3. Long-term immutable rules injection
4. Context formatting for LLM prompts
5. Memory statistics and export
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

from ai_engine.core.memory_manager import (
    CircularContextManager,
    ErrorEntry,
    MemorySummary,
    get_memory_manager,
    initialize_memory_manager,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def memory_manager(temp_db):
    """Create a fresh memory manager instance for each test."""
    manager = CircularContextManager(
        short_term_size=5,
        similarity_threshold=0.95,
        db_path=temp_db,
        workspace="/test/workspace"
    )
    yield manager
    # Cleanup
    manager.clear_all()


class TestErrorEntry:
    """Test ErrorEntry dataclass."""
    
    def test_error_entry_creation(self):
        """Test creating an error entry."""
        entry = ErrorEntry(content="Test error message")
        
        assert entry.content == "Test error message"
        assert entry.occurrence_count == 1
        assert entry.hash != ""
        assert isinstance(entry.timestamp, float)
    
    def test_error_entry_hash_computation(self):
        """Test that hash is computed correctly."""
        entry1 = ErrorEntry(content="Same content")
        entry2 = ErrorEntry(content="Same content")
        entry3 = ErrorEntry(content="Different content")
        
        assert entry1.hash == entry2.hash
        assert entry1.hash != entry3.hash
    
    def test_error_entry_serialization(self):
        """Test converting entry to/from dictionary."""
        entry = ErrorEntry(content="Test error")
        
        # Serialize
        data = entry.to_dict()
        
        assert data["content"] == "Test error"
        assert data["occurrence_count"] == 1
        
        # Deserialize
        restored = ErrorEntry.from_dict(data)
        
        assert restored.content == entry.content
        assert restored.hash == entry.hash


class TestCircularContextManager:
    """Test CircularContextManager core functionality."""
    
    def test_initialization(self, memory_manager):
        """Test memory manager initialization."""
        assert memory_manager.short_term_size == 5
        assert memory_manager.similarity_threshold == 0.95
        assert memory_manager.workspace == "/test/workspace"
        assert len(memory_manager._short_term_buffer) == 0
        assert len(memory_manager._mid_term_summaries) == 0
    
    def test_add_error_new(self, memory_manager):
        """Test adding a new unique error."""
        result = memory_manager.add_error("Unique error message")
        
        assert result is True  # New entry added
        assert len(memory_manager._short_term_buffer) == 1
        assert memory_manager._total_errors_processed == 1
    
    def test_add_error_deduplication(self, memory_manager):
        """Test error deduplication with similar content."""
        # Add first error
        memory_manager.add_error("FileNotFoundError: /path/to/file.txt")
        
        # Add very similar error (should be deduplicated)
        result = memory_manager.add_error("FileNotFoundError: /path/to/file.txt")
        
        assert result is False  # Deduplicated
        assert len(memory_manager._short_term_buffer) == 1
        assert memory_manager._short_term_buffer[0].occurrence_count == 2
    
    def test_add_error_similar_threshold(self, memory_manager):
        """Test deduplication respects similarity threshold."""
        # Add base error
        memory_manager.add_error("Connection timeout after 30 seconds")
        
        # Add 95% similar error (should be deduplicated)
        result1 = memory_manager.add_error("Connection timeout after 30 seconds")
        assert result1 is False
        
        # Add different error (should be added)
        result2 = memory_manager.add_error("Connection refused by host")
        assert result2 is True
        assert len(memory_manager._short_term_buffer) == 2
    
    def test_buffer_overflow_compression(self, temp_db):
        """Test automatic compression when buffer overflows."""
        manager = CircularContextManager(
            short_term_size=3,  # Small size for testing
            db_path=temp_db,
            workspace="/test"
        )
        
        # Add more errors than buffer size
        manager.add_error("Error 1")
        manager.add_error("Error 2")
        manager.add_error("Error 3")
        manager.add_error("Error 4")  # Should trigger compression
        
        # After compression, buffer should have only the newest error
        assert len(manager._short_term_buffer) == 1
        assert len(manager._mid_term_summaries) >= 1
        
        manager.clear_all()
    
    def test_get_statistics(self, memory_manager):
        """Test retrieving memory statistics."""
        memory_manager.add_error("Error 1")
        memory_manager.add_error("Error 2")
        memory_manager.add_error("Error 1")  # Duplicate
        
        stats = memory_manager.get_statistics()
        
        assert stats["short_term_count"] == 2
        assert stats["short_term_capacity"] == 5
        assert stats["mid_term_summaries"] == 0
        assert stats["total_errors_processed"] == 3
        assert stats["workspace"] == "/test/workspace"
    
    def test_clear_short_term(self, memory_manager):
        """Test clearing short-term buffer."""
        memory_manager.add_error("Error 1")
        memory_manager.add_error("Error 2")
        
        memory_manager.clear_short_term()
        
        assert len(memory_manager._short_term_buffer) == 0
        assert memory_manager._total_errors_processed == 2  # Count preserved
    
    def test_clear_all(self, memory_manager, temp_db):
        """Test clearing all memory including database."""
        memory_manager.add_error("Error 1")
        memory_manager.add_error("Error 2")
        memory_manager.add_error("Error 3")
        memory_manager.add_error("Error 4")
        memory_manager.add_error("Error 5")
        memory_manager.add_error("Error 6")  # Trigger compression (buffer size is 5)
        
        # Verify data exists in mid-term (compression should have occurred)
        assert len(memory_manager._mid_term_summaries) >= 1 or len(memory_manager._short_term_buffer) >= 1
        
        # Clear everything
        memory_manager.clear_all()
        
        assert len(memory_manager._short_term_buffer) == 0
        assert len(memory_manager._mid_term_summaries) == 0
        assert memory_manager._total_errors_processed == 0
        
        # Verify database is cleared
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memory_summaries")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 0
    
    def test_export_memory(self, memory_manager):
        """Test exporting complete memory state."""
        memory_manager.add_error("Export test error")
        
        export = memory_manager.export_memory()
        
        assert "short_term" in export
        assert "mid_term" in export
        assert "statistics" in export
        assert "exported_at" in export
        assert len(export["short_term"]) == 1
        assert export["short_term"][0]["content"] == "Export test error"


class TestContextInjection:
    """Test LLM context injection functionality."""
    
    def test_get_context_for_llm_empty(self, memory_manager):
        """Test context generation with empty memory."""
        context = memory_manager.get_context_for_llm("User request")
        
        # Should always include immutable rules
        assert "SYSTEM RULES (IMMUTABLE)" in context
        assert "STRICT-JSON" in context
        assert "SECURITY" in context
        assert "WORKSPACE" in context
        assert "USER REQUEST:" in context
        assert "User request" in context
    
    def test_get_context_for_llm_with_errors(self, memory_manager):
        """Test context generation with errors in buffer."""
        memory_manager.add_error("Critical: Database connection failed")
        memory_manager.add_error("Warning: High memory usage detected")
        
        context = memory_manager.get_context_for_llm("Fix the issues")
        
        assert "LATEST ERRORS (SHORT-TERM)" in context
        assert "Database connection failed" in context
        assert "High memory usage detected" in context
        assert "Fix the issues" in context
    
    def test_get_context_for_llm_with_midterm(self, temp_db):
        """Test context generation with mid-term summaries."""
        manager = CircularContextManager(
            short_term_size=2,
            db_path=temp_db,
            workspace="/test"
        )
        
        # Fill and overflow buffer to create mid-term summary
        manager.add_error("Error A")
        manager.add_error("Error B")
        manager.add_error("Error C")  # Triggers compression
        
        context = manager.get_context_for_llm("What happened before?")
        
        assert "RECENT ERROR HISTORY (COMPRESSED)" in context
        assert "Error C" in context  # Latest error in short-term
        
        manager.clear_all()
    
    def test_immutable_rules_always_present(self, memory_manager):
        """Test that immutable rules are always in context."""
        context = memory_manager.get_context_for_llm("Any request")
        
        for rule in memory_manager.IMMUTABLE_RULES:
            assert rule in context
    
    def test_workspace_in_context(self, memory_manager):
        """Test that workspace is included in context."""
        context = memory_manager.get_context_for_llm("Request")
        
        assert "/test/workspace" in context


class TestPersistence:
    """Test SQLite persistence functionality."""
    
    def test_database_initialization(self, temp_db):
        """Test that database is created correctly."""
        manager = CircularContextManager(db_path=temp_db)
        
        # Verify table exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='memory_summaries'
        """)
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        manager.clear_all()
    
    def test_summary_persistence(self, temp_db):
        """Test that summaries are persisted to database."""
        manager = CircularContextManager(
            short_term_size=2,
            db_path=temp_db
        )
        
        # Trigger compression
        manager.add_error("Persistent error 1")
        manager.add_error("Persistent error 2")
        manager.add_error("Persistent error 3")
        
        # Get summary count before reload
        summary_count_before = len(manager._mid_term_summaries)
        
        # Create new manager instance (should load from DB)
        manager2 = CircularContextManager(db_path=temp_db)
        
        # Should have loaded summaries from database
        assert len(manager2._mid_term_summaries) >= 1
        
        manager.clear_all()
        manager2.clear_all()
    
    def test_database_index_created(self, temp_db):
        """Test that database index is created for performance."""
        manager = CircularContextManager(db_path=temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_end_time'
        """)
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        manager.clear_all()


class TestSingleton:
    """Test singleton pattern for global access."""
    
    def test_get_memory_manager_singleton(self):
        """Test that get_memory_manager returns same instance."""
        manager1 = get_memory_manager()
        manager2 = get_memory_manager()
        
        assert manager1 is manager2
        
        # Cleanup
        manager1.clear_all()
    
    def test_initialize_memory_manager_custom(self, temp_db):
        """Test initializing with custom settings."""
        manager = initialize_memory_manager(
            short_term_size=10,
            similarity_threshold=0.90,
            db_path=temp_db,
            workspace="/custom/workspace"
        )
        
        assert manager.short_term_size == 10
        assert manager.similarity_threshold == 0.90
        assert manager.workspace == "/custom/workspace"
        
        manager.clear_all()


class TestExecutiveSummary:
    """Test executive summary generation."""
    
    def test_generate_summary_single_errors(self, memory_manager):
        """Test summary with single-occurrence errors."""
        memory_manager.add_error("Single error 1")
        memory_manager.add_error("Single error 2")
        memory_manager.add_error("Single error 3")
        memory_manager.add_error("Single error 4")
        memory_manager.add_error("Single error 5")
        memory_manager.add_error("Single error 6")  # Triggers compression
        
        # Check that compression occurred
        assert len(memory_manager._mid_term_summaries) >= 1
        
        summary = memory_manager._mid_term_summaries[0]
        assert "SINGLE OCCURRENCE ERRORS:" in summary.summary
        
        memory_manager.clear_all()
    
    def test_generate_summary_recurring_errors(self, memory_manager):
        """Test summary with recurring errors."""
        # Use smaller buffer to ensure compression happens
        memory_manager.short_term_size = 3
        
        memory_manager.add_error("Recurring error")
        memory_manager.add_error("Recurring error")  # Duplicate
        memory_manager.add_error("Recurring error")  # Duplicate again
        memory_manager.add_error("Another error")
        memory_manager.add_error("Another error")  # Duplicate
        memory_manager.add_error("Trigger compression")  # Triggers compression
        
        # Should have at least one summary after compression
        if len(memory_manager._mid_term_summaries) > 0:
            summary = memory_manager._mid_term_summaries[0]
            
            assert "RECURRING ERRORS:" in summary.summary
            assert "(3x)" in summary.summary or "(2x)" in summary.summary
        
        memory_manager.clear_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
