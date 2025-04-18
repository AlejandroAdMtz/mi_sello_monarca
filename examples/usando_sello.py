from sello_monarca.sello import SelloMonarca

mensaje = b"Acta oficial aprobada por Casa Monarca"

sello = SelloMonarca(
    ruta_llave_privada="keys/private_key.pem",
    ruta_llave_publica="keys/public_key.pem",
    password_privada=b"secreto"
)

firma = sello.firmar_bytes(mensaje)
print("Firma:", firma)

es_valida = sello.verificar_firma(mensaje, firma)
print("Verificación:", "ÉXITO" if es_valida else "FALLÓ")