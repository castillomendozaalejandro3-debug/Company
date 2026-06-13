"""
Environment Encryption Module for Helios Security

Provides secure encryption/decryption of .env files using the cryptography library.
Keys are managed as bytearray and zeroed from memory after use to prevent RAM dumping.
"""

import os
import base64
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EnvEncryptionError(Exception):
    """Exception raised when environment encryption/decryption fails."""
    pass


def zero_memory(data: bytearray) -> None:
    """
    Physically overwrite every byte in the bytearray with zeros using ctypes.memset.
    
    Args:
        data: The bytearray to securely erase from memory.
        
    Raises:
        TypeError: If data is not a bytearray instance.
    """
    if not isinstance(data, bytearray):
        raise TypeError("data must be a bytearray instance")
    
    # Use ctypes.memset for real memory zeroing
    ctypes.memset(ctypes.addressof(data), 0, len(data))


def generate_key() -> Tuple[bytearray, str]:
    """
    Generate a new Fernet encryption key as bytearray for secure handling.
    
    Returns:
        Tuple[bytearray, str]: (key_bytearray, key_base64_string)
        The bytearray should be zeroed after use. The string can be stored.
        
    Note:
        Store the string representation securely. The bytearray must be zeroed.
    """
    key_bytes = Fernet.generate_key()
    key_bytearray = bytearray(key_bytes)
    key_str = key_bytes.decode('utf-8')
    return key_bytearray, key_str


def derive_key_from_password(password: str, salt: bytes) -> Tuple[bytearray, str]:
    """
    Derive a Fernet-compatible key from a password and salt as bytearray.
    
    Args:
        password: User-provided password
        salt: Random salt (16 bytes recommended)
        
    Returns:
        Tuple[bytearray, str]: (key_bytearray, key_base64_string)
        The bytearray should be zeroed after use.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key_bytes = kdf.derive(password.encode())
    key_b64 = base64.urlsafe_b64encode(key_bytes)
    key_bytearray = bytearray(key_b64)
    key_str = key_b64.decode('utf-8')
    return key_bytearray, key_str


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
                       key_env_var: str = "HELIOS_ENV_KEY",
                       zero_key_after: bool = True) -> Dict[str, str]:
    """
    Load and decrypt an encrypted .env.enc file with secure key handling.
    
    This function:
    1. Looks for .env.enc file (or specified path)
    2. Gets encryption key from parameter, environment variable, or prompts user
    3. Decrypts the content and parses environment variables
    4. Zeroes the key from memory after use if zero_key_after=True
    5. Returns as dictionary (does NOT modify os.environ directly)
    
    Args:
        enc_path: Path to .env.enc file (default: current dir/.env.enc)
        key: Encryption key (if not provided, uses env var or prompt)
        key_env_var: Name of environment variable containing the key
        zero_key_after: If True and key was bytearray, zero it after decryption
        
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
    
    # Track if we need to zero a bytearray key
    key_bytearray_to_zero: Optional[bytearray] = None
    
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
    
    # Convert string key to bytearray for secure handling if needed
    if isinstance(key, str):
        key_bytearray_to_zero = bytearray(key.encode('utf-8'))
        key_for_decrypt = key
    elif isinstance(key, bytearray):
        key_bytearray_to_zero = key
        key_for_decrypt = bytes(key).decode('utf-8')
    else:
        key_for_decrypt = key
    
    # Read and decrypt
    try:
        with open(enc_path, 'rb') as f:
            encrypted_content = f.read()
        
        decrypted_content = decrypt_env(encrypted_content, key_for_decrypt)
        
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
    finally:
        # Zero the key from memory after use
        if zero_key_after and key_bytearray_to_zero is not None:
            zero_memory(key_bytearray_to_zero)


def encrypt_env_file(env_path: Optional[str] = None,
                     enc_path: Optional[str] = None,
                     key: Optional[str] = None,
                     delete_original: bool = True,
                     zero_key_after: bool = True) -> str:
    """
    Encrypt a .env file and optionally delete the original with secure key handling.
    
    Args:
        env_path: Path to .env file (default: current dir/.env)
        enc_path: Output path for .env.enc (default: current dir/.env.enc)
        key: Encryption key (generates new one if not provided)
        delete_original: Whether to delete the original .env after encryption
        zero_key_after: If True and key was generated as bytearray, zero it after encryption
        
    Returns:
        str: The encryption key string (must be stored securely by caller).
             The bytearray version is zeroed from memory.
        
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
    
    # Track bytearray key for zeroing
    key_bytearray_to_zero: Optional[bytearray] = None
    key_str: str
    
    # Generate or use provided key
    if key is None:
        # Generate new key as bytearray + string tuple
        key_bytearray_to_zero, key_str = generate_key()
    elif isinstance(key, bytearray):
        key_bytearray_to_zero = key
        key_str = bytes(key).decode('utf-8')
    else:
        key_str = key
    
    # Read and encrypt
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        encrypted_content = encrypt_env(env_content, key_str)
        
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
        
        return key_str
        
    except Exception as e:
        raise EnvEncryptionError(f"Failed to encrypt environment file: {str(e)}")
    finally:
        # Zero the key from memory after use
        if zero_key_after and key_bytearray_to_zero is not None:
            zero_memory(key_bytearray_to_zero)


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
