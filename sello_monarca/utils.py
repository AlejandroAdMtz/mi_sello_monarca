# sello_monarca/utils.py

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


def calcular_hash(data_bytes: bytes) -> bytes:
    """Devuelve el hash SHA-256 de un contenido en bytes"""
    digest = hashes.Hash(hashes.SHA256())
    digest.update(data_bytes)
    return digest.finalize()


def firmar_hash(hash_bytes: bytes, private_key) -> bytes:
    """Firma un hash con la llave privada (RSA + PKCS1v15 + SHA256)"""
    return private_key.sign(
        hash_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )


def verificar_firma(hash_bytes: bytes, firma: bytes, public_key) -> bool:
    """Verifica si la firma digital es válida para un hash y una llave pública"""
    try:
        public_key.verify(
            firma,
            hash_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False


def firma_a_base64(firma: bytes) -> str:
    """Codifica una firma a base64 para guardarla como texto"""
    return base64.b64encode(firma).decode()


def base64_a_firma(firma_b64: str) -> bytes:
    """Decodifica una firma de base64 a bytes"""
    return base64.b64decode(firma_b64)
