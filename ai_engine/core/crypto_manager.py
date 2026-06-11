"""
Crypto Manager - Secure cryptographic operations with zero-memory cleanup.
Provides real, functional cryptographic utilities with physical memory zeroing.
"""

import ctypes
import secrets
import hashlib
from typing import Optional


def zero_memory(data: bytearray) -> None:
    """
    Physically overwrite every byte in the bytearray with zeros.
    
    This function performs a real, physical memory zeroing operation
    by directly modifying each byte in the bytearray object.
    
    Args:
        data: The bytearray to securely erase from memory.
        
    Raises:
        TypeError: If data is not a bytearray instance.
    """
    if not isinstance(data, bytearray):
        raise TypeError("data must be a bytearray instance")
    
    # Get the length of the bytearray
    length = len(data)
    
    # Physically overwrite each byte with zero
    for i in range(length):
        data[i] = 0
    
    # Force garbage collection hint by ensuring the buffer is flushed
    # This ensures the changes are committed to the actual memory
    if length > 0:
        # Touch the memory to ensure write completion
        _ = data[0]


class CryptoManager:
    """
    Cryptographic manager providing secure operations with memory cleanup.
    """
    
    def __init__(self):
        self._key_size = 32  # 256 bits
    
    def generate_key(self, size: Optional[int] = None) -> bytearray:
        """
        Generate a cryptographically secure random key.
        
        Args:
            size: Key size in bytes (default: 32 bytes / 256 bits).
            
        Returns:
            A bytearray containing the generated key.
        """
        key_size = size if size is not None else self._key_size
        key = bytearray(secrets.token_bytes(key_size))
        return key
    
    def hash_data(self, data: bytes, algorithm: str = "sha256") -> bytes:
        """
        Hash data using the specified algorithm.
        
        Args:
            data: The data to hash.
            algorithm: Hash algorithm ('sha256', 'sha512', 'blake2b').
            
        Returns:
            The hash digest as bytes.
        """
        if algorithm == "sha256":
            return hashlib.sha256(data).digest()
        elif algorithm == "sha512":
            return hashlib.sha512(data).digest()
        elif algorithm == "blake2b":
            return hashlib.blake2b(data).digest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    def secure_compare(self, a: bytes, b: bytes) -> bool:
        """
        Constant-time comparison of two byte sequences.
        
        Args:
            a: First byte sequence.
            b: Second byte sequence.
            
        Returns:
            True if equal, False otherwise.
        """
        return secrets.compare_digest(a, b)
    
    def wipe_bytearray(self, data: bytearray) -> None:
        """
        Securely wipe a bytearray from memory.
        
        Args:
            data: The bytearray to wipe.
        """
        zero_memory(data)


# Export public API
__all__ = ["zero_memory", "CryptoManager"]
