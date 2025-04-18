# sello_monarca/pdf_handler.py

from PyPDF2 import PdfReader, PdfWriter
from typing import List, Dict


def leer_pdf_completo(path: str) -> dict:
    """Lee un PDF y devuelve páginas, metadatos y contenido binario"""
    reader = PdfReader(path)
    with open(path, "rb") as f:
        contenido_bytes = f.read()
    return {
        "pages": reader.pages,
        "metadata": reader.metadata,
        "bytes": contenido_bytes
    }


def guardar_pdf(path: str, pages: List, metadata: Dict):
    """Guarda un PDF con páginas y metadatos dados"""
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    writer.add_metadata(metadata)
    with open(path, "wb") as f:
        writer.write(f)


def guardar_pdf_con_firma_pendiente(path_salida: str, path_origen: str, metadata: Dict):
    """Guarda una copia de un PDF con la firma en estado pendiente para cálculo del hash"""
    reader = PdfReader(path_origen)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    metadata_mod = metadata.copy()
    metadata_mod["/FirmaDigital"] = "FIRMA_PENDIENTE"
    writer.add_metadata(metadata_mod)
    with open(path_salida, "wb") as f:
        writer.write(f)
