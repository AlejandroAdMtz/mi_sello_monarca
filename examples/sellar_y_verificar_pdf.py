from sello_monarca.sello import SelloMonarca

# Ruta de llaves
ruta_privada = "keys/private_key.pem"
ruta_publica = "keys/public_key.pem"
password = b"secreto"

# Rutas de PDF
ruta_original = "examples/documento_original.pdf"
ruta_sellado = "examples/documento_sellado.pdf"

# 1. Crear instancia de SelloMonarca
sello = SelloMonarca(
    ruta_llave_privada=ruta_privada,
    ruta_llave_publica=ruta_publica,
    password_privada=password
)

# 2. Sellar el documento original
sello.firmar_pdf(ruta_original, ruta_sellado)
print("✅ Documento sellado y guardado como:", ruta_sellado)

# 3. Verificar la validez del documento sellado
valido = sello.verificar_pdf(ruta_sellado)
print("🔍 Resultado de la verificación:", "VÁLIDO ✅" if valido else "NO VÁLIDO ❌")
