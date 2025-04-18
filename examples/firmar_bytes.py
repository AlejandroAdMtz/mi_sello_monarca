# examples/firmar_bytes.py

from sello_monarca.llaves import cargar_llave_privada, cargar_llave_publica
from sello_monarca.utils import calcular_hash, firmar_hash, verificar_firma, firma_a_base64, base64_a_firma

# --- CONFIGURACIÓN ---
mensaje = b"Este es un mensaje de prueba firmado por Sello Monarca"
ruta_privada = "keys/private_key.pem"
ruta_publica = "keys/public_key.pem"
password = b"secreto"

# --- CARGAR LLAVES ---
private_key = cargar_llave_privada(ruta_privada, password)
public_key = cargar_llave_publica(ruta_publica)

# --- FIRMAR ---
hash_mensaje = calcular_hash(mensaje)
firma = firmar_hash(hash_mensaje, private_key)
firma_b64 = firma_a_base64(firma)

print("🔏 Firma (base64):")
print(firma_b64)

# --- VERIFICAR ---
firma_bytes = base64_a_firma(firma_b64)
es_valida = verificar_firma(hash_mensaje, firma_bytes, public_key)

print("\nVerificación de firma:", "VÁLIDA" if es_valida else "NO VÁLIDA")
