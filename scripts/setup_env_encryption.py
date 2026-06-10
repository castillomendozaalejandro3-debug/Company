"""
Setup script for encrypting .env files in Helios AI Engine.

This script:
1. Reads the existing .env file
2. Generates a new encryption key (or uses provided one)
3. Encrypts the .env content
4. Saves as .env.enc
5. Securely deletes the original .env file

Usage:
    python scripts/setup_env_encryption.py [--key YOUR_KEY] [--output PATH]
    
Environment Variables:
    HELIOS_ENV_KEY: Use this key for encryption instead of generating new one
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ai_engine.core.security.env_encryptor import (
        encrypt_env_file,
        generate_key,
        EnvEncryptionError,
    )
except ImportError as e:
    print(f"Error importing encryption module: {e}")
    print("\nMake sure cryptography library is installed:")
    print("  pip install cryptography")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt .env file for Helios AI Engine"
    )
    parser.add_argument(
        "--env-path",
        type=str,
        default=None,
        help="Path to .env file (default: current directory/.env)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for .env.enc (default: current directory/.env.enc)"
    )
    parser.add_argument(
        "--key",
        type=str,
        default=None,
        help="Encryption key (generates new one if not provided)"
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="Keep the original .env file after encryption (NOT RECOMMENDED)"
    )
    parser.add_argument(
        "--show-key",
        action="store_true",
        help="Display the encryption key (use with caution)"
    )
    
    args = parser.parse_args()
    
    # Check if .env exists
    env_path = Path(args.env_path) if args.env_path else Path.cwd() / ".env"
    
    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}")
        print("\nPlease create a .env file first with your environment variables.")
        sys.exit(1)
    
    # Get encryption key
    key = args.key or os.environ.get("HELIOS_ENV_KEY")
    
    if key:
        print("Using provided encryption key...")
    else:
        print("Generating new encryption key...")
        key = generate_key()
    
    # Determine output path
    enc_path = Path(args.output) if args.output else Path.cwd() / ".env.enc"
    
    print(f"\nEncrypting: {env_path}")
    print(f"Output: {enc_path}")
    
    try:
        # Perform encryption
        result_key = encrypt_env_file(
            env_path=str(env_path),
            enc_path=str(enc_path),
            key=key,
            delete_original=not args.keep_original
        )
        
        print("\n✓ Encryption successful!")
        print(f"✓ Encrypted file created: {enc_path}")
        
        if not args.keep_original:
            print(f"✓ Original .env file securely deleted")
        
        # Display key warning
        print("\n" + "=" * 60)
        print("IMPORTANT: Save this encryption key securely!")
        print("=" * 60)
        
        if args.show_key:
            print(f"\nENCRYPTION KEY: {result_key}")
        else:
            print("\nThe encryption key has been generated but not displayed.")
            print("Use --show-key to display it (be careful who can see it).")
        
        print("\nStore the key in a secure location:")
        print("  - Password manager")
        print("  - Secure vault")
        print("  - Environment variable HELIOS_ENV_KEY (for automated deployments)")
        print("\nTo decrypt and use the .env.enc file, set:")
        print(f"  export HELIOS_ENV_KEY=\"{result_key}\"")
        print("=" * 60)
        
        return 0
        
    except EnvEncryptionError as e:
        print(f"\n✗ Encryption failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
