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
    

from cryptography.hazmat.primitives import serialization

def cargar_llave_privada_desde_env(env_string: str, password: bytes | None = None):
    """
    Recibe la clave privada como string desde el .env (con \n escapados) y devuelve el objeto clave.
    """
    if not env_string:
        raise ValueError("La variable de entorno de la clave privada está vacía")

    key_cleaned = env_string.strip().strip('"').strip("'")  # quita comillas y espacios
    key_bytes = key_cleaned.encode("utf-8").decode("unicode_escape").encode("utf-8")

    return serialization.load_pem_private_key(key_bytes, password=password)


def cargar_llave_publica_desde_env(env_string: str):
    """
    Recibe la clave pública como string desde el .env (con \n escapados) y devuelve el objeto clave.
    """
    if not env_string:
        raise ValueError("La variable de entorno de la clave pública está vacía")

    key_cleaned = env_string.strip().strip('"').strip("'")
    key_bytes = key_cleaned.encode("utf-8").decode("unicode_escape").encode("utf-8")

    return serialization.load_pem_public_key(key_bytes)
