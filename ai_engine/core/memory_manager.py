"""
Circular Context Manager for Helios AI Engine

Implements a Token-Buffer Pattern with three-tier memory hierarchy:
- Short-Term Buffer: Recent errors with deduplication (deque, maxlen=5)
- Mid-Term Memory: Compressed summaries of recent errors (SQLite persistence)
- Long-Term Memory: Immutable rules and workspace context (always injected)

This prevents LLM hallucination and token saturation while maintaining
contextual awareness of errors and security constraints.
"""

import hashlib
import json
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher


@dataclass
class ErrorEntry:
    """Represents a single error entry in short-term memory."""
    content: str
    timestamp: float = field(default_factory=time.time)
    occurrence_count: int = 1
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute SHA256 hash of error content for deduplication."""
        return hashlib.sha256(self.content.encode('utf-8')).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ErrorEntry':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class MemorySummary:
    """Represents a compressed summary in mid-term memory."""
    summary: str
    error_count: int
    start_time: float
    end_time: float
    error_hashes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemorySummary':
        return cls(**data)


class CircularContextManager:
    """
    Manages hierarchical memory for Helios AI using Token-Buffer Pattern.
    
    Three-tier architecture:
    1. Short-Term Buffer: Last 5 unique errors with deduplication
    2. Mid-Term Memory: Compressed summaries persisted to SQLite
    3. Long-Term Memory: Immutable rules always injected to LLM
    
    Features:
    - 95% similarity deduplication for errors
    - Occurrence counting for repeated errors
    - Automatic compression when buffer fills
    - SQLite persistence for restart resilience
    - Token-efficient context injection
    """
    
    # Default configuration
    DEFAULT_SHORT_TERM_SIZE = 5
    DEFAULT_SIMILARITY_THRESHOLD = 0.95
    DEFAULT_DB_PATH = "helios_memory.db"
    
    # Immutable rules (Long-Term Memory)
    IMMUTABLE_RULES = [
        "STRICT-JSON: Always respond with valid JSON format",
        "SECURITY: Never execute commands that compromise system integrity",
        "WORKSPACE: All file operations must stay within workspace boundary",
        "NO-EVAL: Never use eval() or exec() functions",
        "PATH-SAFETY: Validate all paths against path traversal attacks",
        "LOG-AUDIT: Log all security-sensitive operations",
    ]
    
    def __init__(
        self,
        short_term_size: int = DEFAULT_SHORT_TERM_SIZE,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        db_path: Optional[str] = None,
        workspace: Optional[str] = None
    ):
        """
        Initialize the Circular Context Manager.
        
        Args:
            short_term_size: Maximum size of short-term error buffer
            similarity_threshold: Threshold for error deduplication (0.0-1.0)
            db_path: Path to SQLite database for mid-term persistence
            workspace: Workspace directory path for context
        """
        self.short_term_size = short_term_size
        self.similarity_threshold = similarity_threshold
        self.workspace = workspace or str(Path.cwd())
        
        # Short-Term Buffer: Deque for O(1) append/pop
        self._short_term_buffer: deque[ErrorEntry] = deque(maxlen=short_term_size)
        
        # Mid-Term Memory: List of summaries (loaded from SQLite)
        self._mid_term_summaries: List[MemorySummary] = []
        
        # Database path
        self._db_path = db_path or self.DEFAULT_DB_PATH
        
        # Initialize SQLite storage
        self._init_database()
        
        # Load persisted mid-term memory
        self._load_mid_term_memory()
        
        # Track total errors processed
        self._total_errors_processed = 0
    
    def _init_database(self) -> None:
        """Initialize SQLite database for mid-term memory persistence."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            # Create table for memory summaries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    error_count INTEGER NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    error_hashes TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create index for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_end_time 
                ON memory_summaries(end_time)
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            # Log but don't fail - memory manager should be resilient
            print(f"[MEMORY] Warning: Could not initialize database: {e}")
    
    def _load_mid_term_memory(self) -> None:
        """Load mid-term summaries from SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT summary, error_count, start_time, end_time, error_hashes
                FROM memory_summaries
                ORDER BY end_time DESC
                LIMIT 10
            ''')
            
            rows = cursor.fetchall()
            for row in rows:
                summary = MemorySummary(
                    summary=row[0],
                    error_count=row[1],
                    start_time=row[2],
                    end_time=row[3],
                    error_hashes=json.loads(row[4]) if row[4] else []
                )
                self._mid_term_summaries.append(summary)
            
            conn.close()
            
        except Exception as e:
            print(f"[MEMORY] Warning: Could not load mid-term memory: {e}")
            self._mid_term_summaries = []
    
    def _save_summary_to_db(self, summary: MemorySummary) -> None:
        """Persist a summary to SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO memory_summaries 
                (summary, error_count, start_time, end_time, error_hashes)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                summary.summary,
                summary.error_count,
                summary.start_time,
                summary.end_time,
                json.dumps(summary.error_hashes)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"[MEMORY] Warning: Could not save summary to database: {e}")
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute similarity ratio between two texts.
        
        Uses SequenceMatcher for efficient string comparison.
        Returns value between 0.0 (completely different) and 1.0 (identical).
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            float: Similarity ratio (0.0 to 1.0)
        """
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _find_similar_error(self, new_content: str) -> Optional[ErrorEntry]:
        """
        Find a similar error in the short-term buffer.
        
        Args:
            new_content: Content of the new error
            
        Returns:
            ErrorEntry if similar error found, None otherwise
        """
        for entry in self._short_term_buffer:
            similarity = self._compute_similarity(new_content, entry.content)
            if similarity >= self.similarity_threshold:
                return entry
        return None
    
    def add_error(self, error_content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add an error to the short-term buffer with deduplication.
        
        If a similar error exists (>=95% similarity), increment occurrence count.
        Otherwise, add as new entry.
        
        When buffer is full, compress to mid-term memory automatically.
        
        Args:
            error_content: The error message/stack trace content
            metadata: Optional additional metadata
            
        Returns:
            bool: True if added as new entry, False if deduplicated
        """
        self._total_errors_processed += 1
        
        # Check for similar existing error
        similar_entry = self._find_similar_error(error_content)
        
        if similar_entry is not None:
            # Deduplicate: increment occurrence count
            similar_entry.occurrence_count += 1
            print(f"[MEMORY] Deduplicated error (count: {similar_entry.occurrence_count})")
            return False
        
        # Check if buffer is full - need to compress before adding
        if len(self._short_term_buffer) >= self.short_term_size:
            self._compress_to_mid_term()
        
        # Add new error entry
        new_entry = ErrorEntry(content=error_content)
        self._short_term_buffer.append(new_entry)
        
        print(f"[MEMORY] Added new error to short-term buffer")
        return True
    
    def _compress_to_mid_term(self) -> Optional[MemorySummary]:
        """
        Compress short-term buffer to a mid-term summary.
        
        Creates an executive summary of all errors in the buffer,
        saves to SQLite, and clears the buffer.
        
        Returns:
            MemorySummary if compression successful, None otherwise
        """
        if not self._short_term_buffer:
            return None
        
        # Gather all errors
        errors = list(self._short_term_buffer)
        total_occurrences = sum(e.occurrence_count for e in errors)
        
        # Generate executive summary
        summary_text = self._generate_executive_summary(errors)
        
        # Create summary object
        summary = MemorySummary(
            summary=summary_text,
            error_count=len(errors),
            start_time=min(e.timestamp for e in errors),
            end_time=max(e.timestamp for e in errors),
            error_hashes=[e.hash for e in errors]
        )
        
        # Persist to SQLite
        self._mid_term_summaries.insert(0, summary)
        self._save_summary_to_db(summary)
        
        # Clear short-term buffer
        self._short_term_buffer.clear()
        
        print(f"[MEMORY] Compressed {len(errors)} errors to mid-term summary")
        return summary
    
    def _generate_executive_summary(self, errors: List[ErrorEntry]) -> str:
        """
        Generate an executive summary of errors.
        
        Args:
            errors: List of error entries to summarize
            
        Returns:
            str: Concise summary text
        """
        if not errors:
            return "No errors recorded."
        
        # Group by occurrence count
        frequent_errors = [e for e in errors if e.occurrence_count > 1]
        single_errors = [e for e in errors if e.occurrence_count == 1]
        
        summary_parts = []
        
        # Report frequent/recurring errors first
        if frequent_errors:
            summary_parts.append("RECURRING ERRORS:")
            for err in sorted(frequent_errors, key=lambda x: x.occurrence_count, reverse=True):
                # Truncate long error messages
                content = err.content[:200] + "..." if len(err.content) > 200 else err.content
                summary_parts.append(f"  - ({err.occurrence_count}x) {content}")
        
        # Report single-occurrence errors
        if single_errors:
            summary_parts.append("SINGLE OCCURRENCE ERRORS:")
            for err in single_errors[:3]:  # Limit to 3 for brevity
                content = err.content[:150] + "..." if len(err.content) > 150 else err.content
                summary_parts.append(f"  - {content}")
            if len(single_errors) > 3:
                summary_parts.append(f"  ... and {len(single_errors) - 3} more")
        
        return "\n".join(summary_parts)
    
    def get_context_for_llm(self, user_message: str) -> str:
        """
        Build the complete context to inject into LLM prompt.
        
        Combines:
        1. Long-term immutable rules (always included)
        2. Mid-term memory summaries (recent history)
        3. Short-term buffer (latest errors)
        4. User's current message
        
        Args:
            user_message: The user's current message/request
            
        Returns:
            str: Complete formatted context for LLM
        """
        context_parts = []
        
        # 1. LONG-TERM MEMORY: Immutable rules (always first)
        context_parts.append("=" * 60)
        context_parts.append("SYSTEM RULES (IMMUTABLE):")
        context_parts.append("=" * 60)
        for rule in self.IMMUTABLE_RULES:
            context_parts.append(f"  • {rule}")
        
        # Add workspace context
        context_parts.append(f"\n  • WORKSPACE: {self.workspace}")
        
        # 2. MID-TERM MEMORY: Recent summaries (if any)
        if self._mid_term_summaries:
            context_parts.append("\n" + "=" * 60)
            context_parts.append("RECENT ERROR HISTORY (COMPRESSED):")
            context_parts.append("=" * 60)
            # Include last 3 summaries for context
            for i, summary in enumerate(self._mid_term_summaries[:3]):
                context_parts.append(f"\n[History Block {i+1}]")
                context_parts.append(f"Errors: {summary.error_count}")
                context_parts.append(f"Time span: {datetime.fromtimestamp(summary.start_time).strftime('%H:%M:%S')} - {datetime.fromtimestamp(summary.end_time).strftime('%H:%M:%S')}")
                context_parts.append(summary.summary)
        
        # 3. SHORT-TERM MEMORY: Latest errors
        if self._short_term_buffer:
            context_parts.append("\n" + "=" * 60)
            context_parts.append("LATEST ERRORS (SHORT-TERM):")
            context_parts.append("=" * 60)
            for i, entry in enumerate(self._short_term_buffer):
                suffix = ""
                if entry.occurrence_count > 1:
                    suffix = f" [REPEATED {entry.occurrence_count} TIMES]"
                context_parts.append(f"\n[Error {i+1}]{suffix}")
                # Truncate very long errors
                content = entry.content[:300] + "..." if len(entry.content) > 300 else entry.content
                context_parts.append(content)
        
        # 4. USER MESSAGE
        context_parts.append("\n" + "=" * 60)
        context_parts.append("USER REQUEST:")
        context_parts.append("=" * 60)
        context_parts.append(user_message)
        
        return "\n".join(context_parts)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get memory usage statistics.
        
        Returns:
            Dictionary with memory statistics
        """
        return {
            "short_term_count": len(self._short_term_buffer),
            "short_term_capacity": self.short_term_size,
            "mid_term_summaries": len(self._mid_term_summaries),
            "total_errors_processed": self._total_errors_processed,
            "unique_errors_in_buffer": len(set(e.hash for e in self._short_term_buffer)),
            "workspace": self.workspace,
            "database_path": self._db_path
        }
    
    def clear_short_term(self) -> None:
        """Clear the short-term buffer (manual reset)."""
        self._short_term_buffer.clear()
        print("[MEMORY] Short-term buffer cleared")
    
    def clear_all(self) -> None:
        """Clear all memory (short-term and mid-term)."""
        self.clear_short_term()
        self._mid_term_summaries.clear()
        
        # Also clear database
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_summaries")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MEMORY] Warning: Could not clear database: {e}")
        
        self._total_errors_processed = 0
        print("[MEMORY] All memory cleared")
    
    def export_memory(self) -> Dict[str, Any]:
        """
        Export complete memory state for debugging/backup.
        
        Returns:
            Dictionary containing full memory state
        """
        return {
            "short_term": [e.to_dict() for e in self._short_term_buffer],
            "mid_term": [s.to_dict() for s in self._mid_term_summaries],
            "statistics": self.get_statistics(),
            "exported_at": datetime.now().isoformat()
        }


# Singleton instance for global access
_memory_manager: Optional[CircularContextManager] = None


def get_memory_manager() -> CircularContextManager:
    """
    Get the global memory manager instance (singleton pattern).
    
    Returns:
        CircularContextManager: The global instance
    """
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = CircularContextManager()
    return _memory_manager


def initialize_memory_manager(
    short_term_size: int = 5,
    similarity_threshold: float = 0.95,
    db_path: Optional[str] = None,
    workspace: Optional[str] = None
) -> CircularContextManager:
    """
    Initialize the global memory manager with custom settings.
    
    Args:
        short_term_size: Size of short-term buffer
        similarity_threshold: Deduplication threshold
        db_path: SQLite database path
        workspace: Workspace directory
        
    Returns:
        CircularContextManager: The initialized instance
    """
    global _memory_manager
    _memory_manager = CircularContextManager(
        short_term_size=short_term_size,
        similarity_threshold=similarity_threshold,
        db_path=db_path,
        workspace=workspace
    )
    return _memory_manager
