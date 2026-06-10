"""
Environment Encryption Module for Helios Security

Provides secure encryption/decryption of .env files using the cryptography library.
Keys are never stored in plain text and must be provided via environment variable or prompt.
"""

import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EnvEncryptionError(Exception):
    """Exception raised when environment encryption/decryption fails."""
    pass


def generate_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Returns:
        str: Base64-encoded 32-byte key suitable for Fernet
        
    Note:
        Store this key securely. It cannot be recovered if lost.
    """
    return Fernet.generate_key().decode('utf-8')


def derive_key_from_password(password: str, salt: bytes) -> str:
    """
    Derive a Fernet-compatible key from a password and salt.
    
    Args:
        password: User-provided password
        salt: Random salt (16 bytes recommended)
        
    Returns:
        str: Base64-encoded key suitable for Fernet
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key.decode('utf-8')


def encrypt_env(env_content: str, key: str) -> bytes:
    """
    Encrypt environment file content.
    
    Args:
        env_content: Plain text content of .env file
        key: Fernet encryption key
        
    Returns:
        bytes: Encrypted content with authentication tag
        
    Raises:
        EnvEncryptionError: If encryption fails
    """
    try:
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        encrypted = fernet.encrypt(env_content.encode('utf-8'))
        return encrypted
    except Exception as e:
        raise EnvEncryptionError(f"Failed to encrypt environment: {str(e)}")


def decrypt_env(encrypted_content: bytes, key: str) -> str:
    """
    Decrypt environment file content.
    
    Args:
        encrypted_content: Encrypted bytes from encrypt_env()
        key: Fernet encryption key
        
    Returns:
        str: Decrypted plain text content
        
    Raises:
        EnvEncryptionError: If decryption fails (wrong key or corrupted data)
    """
    try:
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        decrypted = fernet.decrypt(encrypted_content)
        return decrypted.decode('utf-8')
    except Exception as e:
        raise EnvEncryptionError(f"Failed to decrypt environment: Invalid key or corrupted data")


def load_encrypted_env(enc_path: Optional[str] = None, 
                       key: Optional[str] = None,
                       key_env_var: str = "HELIOS_ENV_KEY") -> Dict[str, str]:
    """
    Load and decrypt an encrypted .env.enc file.
    
    This function:
    1. Looks for .env.enc file (or specified path)
    2. Gets encryption key from parameter, environment variable, or prompts user
    3. Decrypts the content and parses environment variables
    4. Returns as dictionary (does NOT modify os.environ directly)
    
    Args:
        enc_path: Path to .env.enc file (default: current dir/.env.enc)
        key: Encryption key (if not provided, uses env var or prompt)
        key_env_var: Name of environment variable containing the key
        
    Returns:
        Dict[str, str]: Dictionary of environment variables
        
    Raises:
        EnvEncryptionError: If file not found, key invalid, or decryption fails
        FileNotFoundError: If .env.enc does not exist
    """
    # Determine path to encrypted file
    if enc_path is None:
        enc_path = Path.cwd() / ".env.enc"
    else:
        enc_path = Path(enc_path)
    
    if not enc_path.exists():
        raise FileNotFoundError(f"Encrypted environment file not found: {enc_path}")
    
    # Get encryption key
    if key is None:
        key = os.environ.get(key_env_var)
    
    if key is None:
        # Prompt user for key (securely - no echo on supported systems)
        import getpass
        print(f"Enter encryption key for {enc_path}: ", end="", flush=True)
        key = getpass.getpass("")
    
    if not key:
        raise EnvEncryptionError("No encryption key provided")
    
    # Read and decrypt
    try:
        with open(enc_path, 'rb') as f:
            encrypted_content = f.read()
        
        decrypted_content = decrypt_env(encrypted_content, key)
        
        # Parse environment variables
        env_vars = {}
        for line in decrypted_content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE
            if '=' in line:
                key_name, _, value = line.partition('=')
                key_name = key_name.strip()
                value = value.strip()
                # Handle quoted values
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                env_vars[key_name] = value
        
        return env_vars
        
    except FileNotFoundError:
        raise
    except EnvEncryptionError:
        raise
    except Exception as e:
        raise EnvEncryptionError(f"Error loading encrypted environment: {str(e)}")


def encrypt_env_file(env_path: Optional[str] = None,
                     enc_path: Optional[str] = None,
                     key: Optional[str] = None,
                     delete_original: bool = True) -> str:
    """
    Encrypt a .env file and optionally delete the original.
    
    Args:
        env_path: Path to .env file (default: current dir/.env)
        enc_path: Output path for .env.enc (default: current dir/.env.enc)
        key: Encryption key (generates new one if not provided)
        delete_original: Whether to delete the original .env after encryption
        
    Returns:
        str: The encryption key used (must be stored securely by caller)
        
    Raises:
        EnvEncryptionError: If encryption fails
        FileNotFoundError: If .env file not found
    """
    # Determine paths
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)
    
    if enc_path is None:
        enc_path = Path.cwd() / ".env.enc"
    else:
        enc_path = Path(enc_path)
    
    if not env_path.exists():
        raise FileNotFoundError(f"Environment file not found: {env_path}")
    
    # Generate or use provided key
    if key is None:
        key = generate_key()
    
    # Read and encrypt
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        encrypted_content = encrypt_env(env_content, key)
        
        # Write encrypted file
        with open(enc_path, 'wb') as f:
            f.write(encrypted_content)
        
        # Set restrictive permissions on encrypted file
        try:
            os.chmod(enc_path, 0o600)  # Owner read/write only
        except OSError:
            pass  # May fail on Windows, continue anyway
        
        # Delete original if requested
        if delete_original:
            os.remove(env_path)
        
        return key
        
    except Exception as e:
        raise EnvEncryptionError(f"Failed to encrypt environment file: {str(e)}")


def apply_env_to_os(env_vars: Dict[str, str], overwrite: bool = False) -> None:
    """
    Apply environment variables to os.environ.
    
    Args:
        env_vars: Dictionary of environment variables
        overwrite: Whether to overwrite existing variables
        
    Note:
        This modifies the current process environment only.
    """
    for key, value in env_vars.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
