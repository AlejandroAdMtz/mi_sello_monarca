from sello_monarca.llaves import generar_llaves

# Rutas donde se guardarán las llaves
ruta_privada = "keys/private_key.pem"
ruta_publica = "keys/public_key.pem"

# Generar las llaves con contraseña 'secreto'
generar_llaves(ruta_privada, ruta_publica, password=b"secreto")

print("Llaves generadas correctamente y guardadas en la carpeta 'keys'")
