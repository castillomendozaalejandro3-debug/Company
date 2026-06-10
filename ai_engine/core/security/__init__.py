"""
Security Module for Helios AI Engine

Provides security utilities including path validation and environment encryption.
"""

from .path_validator import validate_path, is_safe_path, sanitize_path, PathValidationError
from .env_encryptor import (
    generate_key,
    derive_key_from_password,
    encrypt_env,
    decrypt_env,
    load_encrypted_env,
    encrypt_env_file,
    apply_env_to_os,
    EnvEncryptionError,
)

__all__ = [
    # Path validation
    "validate_path",
    "is_safe_path", 
    "sanitize_path",
    "PathValidationError",
    # Environment encryption
    "generate_key",
    "derive_key_from_password",
    "encrypt_env",
    "decrypt_env",
    "load_encrypted_env",
    "encrypt_env_file",
    "apply_env_to_os",
    "EnvEncryptionError",
]
