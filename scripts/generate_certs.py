#!/usr/bin/env python3
"""
Generador de Certificados X.509 Efímeros para mTLS.
Genera certificados en memoria sin tocar disco para comunicación Kernel-Workers.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

def generate_ca_certificate(validity_days: int = 365):
    """Genera una CA raíz efímera."""
    # Generar clave privada RSA
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Crear sujeto y emisor (mismo para CA raíz)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Helios AI"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Helios Root CA"),
    ])
    
    # Construir certificado
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=1),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    
    return private_key, cert

def generate_worker_certificate(ca_private_key, ca_cert, worker_id: str, validity_days: int = 30):
    """Genera un certificado de worker firmado por la CA."""
    # Generar clave privada para el worker
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Crear sujeto específico para el worker
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Helios AI"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Workers"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"worker-{worker_id}"),
    ])
    
    # Construir certificado firmado por la CA
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.OID_SERVER_AUTH,
                x509.OID_CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(ca_private_key, hashes.SHA256(), default_backend())
    )
    
    return private_key, cert

def serialize_to_pem(private_key, cert):
    """Serializa clave y certificado a formato PEM (en memoria)."""
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    
    return key_pem, cert_pem

def main():
    """Genera certificados mTLS para Helios."""
    print("=" * 50)
    print("  HELIOS AI - mTLS Certificate Generator")
    print("=" * 50)
    print()
    
    # Generar CA
    print("[1/3] Generating Root CA...")
    ca_key, ca_cert = generate_ca_certificate(validity_days=365)
    ca_key_pem, ca_cert_pem = serialize_to_pem(ca_key, ca_cert)
    print(f"      CA Common Name: {ca_cert.subject.rfc4514_string()}")
    print(f"      Valid until: {ca_cert.not_valid_after_utc}")
    
    # Generar certificado para Kernel
    print("[2/3] Generating Kernel certificate...")
    kernel_key, kernel_cert = generate_worker_certificate(ca_key, ca_cert, "kernel", validity_days=90)
    kernel_key_pem, kernel_cert_pem = serialize_to_pem(kernel_key, kernel_cert)
    print(f"      Kernel CN: {kernel_cert.subject.rfc4514_string()}")
    
    # Generar certificado para Worker ejemplo
    print("[3/3] Generating sample Worker certificate...")
    worker_key, worker_cert = generate_worker_certificate(ca_key, ca_cert, "001", validity_days=30)
    worker_key_pem, worker_cert_pem = serialize_to_pem(worker_key, worker_cert)
    print(f"      Worker CN: {worker_cert.subject.rfc4514_string()}")
    
    print()
    print("=" * 50)
    print("  CERTIFICATES GENERATED (IN MEMORY)")
    print("=" * 50)
    print()
    print("CA Certificate PEM:")
    print("-" * 40)
    print(ca_cert_pem.decode()[:200] + "...")
    print()
    print("Kernel Certificate PEM:")
    print("-" * 40)
    print(kernel_cert_pem.decode()[:200] + "...")
    print()
    print("Worker Certificate PEM:")
    print("-" * 40)
    print(worker_cert_pem.decode()[:200] + "...")
    print()
    print("NOTE: Certificates are ephemeral and stored only in memory.")
    print("      Use IPC to distribute to Kernel and Workers securely.")
    print()
    
    return {
        "ca": {"key": ca_key_pem, "cert": ca_cert_pem},
        "kernel": {"key": kernel_key_pem, "cert": kernel_cert_pem},
        "worker": {"key": worker_key_pem, "cert": worker_cert_pem}
    }

if __name__ == "__main__":
    certs = main()
