# sello_monarca/sello.py

from sello_monarca.llaves import cargar_llave_privada, cargar_llave_publica
from sello_monarca.utils import (
    calcular_hash,
    firmar_hash,
    verificar_firma,
    firma_a_base64,
    base64_a_firma
)
from sello_monarca.pdf_handler import leer_pdf_completo, guardar_pdf, guardar_pdf_con_firma_pendiente

from datetime import datetime

class SelloMonarca:
    def __init__(self, ruta_llave_privada=None, ruta_llave_publica=None, password_privada=b'secreto'):
        self.ruta_llave_privada = ruta_llave_privada
        self.ruta_llave_publica = ruta_llave_publica
        self.password = password_privada
        self.private_key = None
        self.public_key = None

        if ruta_llave_privada:
            self.private_key = cargar_llave_privada(ruta_llave_privada, password_privada)
        if ruta_llave_publica:
            self.public_key = cargar_llave_publica(ruta_llave_publica)

    def firmar_bytes(self, data: bytes) -> str:
        if not self.private_key:
            raise ValueError("No se ha cargado la llave privada.")
        hash_data = calcular_hash(data)
        firma = firmar_hash(hash_data, self.private_key)
        return firma_a_base64(firma)

    def verificar_firma(self, data: bytes, firma_b64: str) -> bool:
        if not self.public_key:
            raise ValueError("No se ha cargado la llave pública.")
        hash_data = calcular_hash(data)
        firma = base64_a_firma(firma_b64)
        return verificar_firma(hash_data, firma, self.public_key)

    def firmar_pdf(self, path_pdf_original: str, path_pdf_sellado: str):
        if not self.private_key:
            raise ValueError("No se ha cargado la llave privada.")

        # 1. Crear metadatos base
        metadatos_base = {
            "/Author": "Casa Monarca",
            "/Title": "Documento Sellado Oficialmente",
            "/Subject": "Sello Monarca con firma digital",
            "/ModDate": f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "/EntidadSelladora": "Casa Monarca",
            "/FirmaDigital": "FIRMA_PENDIENTE"
        }

        # 2. Guardar versión temporal sin la firma
        temp_path = "temp_sin_firma.pdf"
        guardar_pdf_con_firma_pendiente(temp_path, path_pdf_original, metadatos_base)

        # 3. Calcular hash de esa versión
        contenido_sin_firma = leer_pdf_completo(temp_path)["bytes"]
        hash_temp = calcular_hash(contenido_sin_firma)

        # 4. Firmar y codificar
        firma = firmar_hash(hash_temp, self.private_key)
        firma_b64 = firma_a_base64(firma)

        # 5. Volver a leer el PDF y guardar con firma real
        datos_finales = leer_pdf_completo(temp_path)
        metadatos_base["/FirmaDigital"] = firma_b64
        guardar_pdf(path_pdf_sellado, datos_finales["pages"], metadatos_base)

    def verificar_pdf(self, path_pdf: str) -> bool:
        if not self.public_key:
            raise ValueError("No se ha cargado la llave pública.")

        # 1. Leer PDF completo
        datos_pdf = leer_pdf_completo(path_pdf)
        firma_b64 = datos_pdf["metadata"].get("/FirmaDigital", "")
        if not firma_b64 or firma_b64 == "FIRMA_PENDIENTE":
            print("No se encontró firma válida.")
            return False

        # 2. Crear versión temporal sin la firma
        temp_path = "temp_verificacion.pdf"
        metadatos_temp = dict(datos_pdf["metadata"])
        metadatos_temp["/FirmaDigital"] = "FIRMA_PENDIENTE"
        guardar_pdf(temp_path, datos_pdf["pages"], metadatos_temp)

        # 3. Calcular hash del contenido sin firma
        contenido_sin_firma = leer_pdf_completo(temp_path)["bytes"]
        hash_verificacion = calcular_hash(contenido_sin_firma)

        # 4. Verificar
        firma = base64_a_firma(firma_b64)
        return verificar_firma(hash_verificacion, firma, self.public_key)
