# sello_monarca/llaves.py

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import ec



def generar_llaves(ruta_privada, ruta_publica, password: bytes = b'secreto'):
    """Genera un par de llaves RSA y las guarda en archivos .pem"""

    private_key = ec.generate_private_key(ec.SECP256R1())

    """""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    """""
    # Guardar llave privada con cifrado por contraseña
    pem_privada = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password)
    )
    with open(ruta_privada, "wb") as f:
        f.write(pem_privada)

    # Guardar llave pública
    public_key = private_key.public_key()
    pem_publica = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(ruta_publica, "wb") as f:
        f.write(pem_publica)


def cargar_llave_privada(ruta, password: bytes):
    """Carga una llave privada desde un archivo .pem"""
    with open(ruta, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=password)


def cargar_llave_publica(ruta):
    """Carga una llave pública desde un archivo .pem"""
    with open(ruta, "rb") as f:
        return serialization.load_pem_public_key(f.read())
