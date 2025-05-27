# sello_monarca/llaves.py

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def generar_llaves(ruta_priv, ruta_pub, password=b"secreto"):
    key = ec.generate_private_key(ec.SECP256R1())
    pem_priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password)
    )
    open(ruta_priv, "wb").write(pem_priv)

    pem_pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    )
    open(ruta_pub, "wb").write(pem_pub)

def cargar_llave_privada(ruta, password: bytes):
    """Carga una llave privada desde un archivo .pem"""
    with open(ruta, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=password)


def cargar_llave_publica(ruta):
    """Carga una llave pública desde un archivo .pem"""
    with open(ruta, "rb") as f:
        return serialization.load_pem_public_key(f.read())
