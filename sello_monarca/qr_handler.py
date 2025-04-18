# sello_monarca/qr_handler.py

import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

def generar_pagina_qr(url: str, salida_pdf: str):
    """Genera una página PDF con un QR grande al centro que apunta a una URL"""
    qr = qrcode.make(url)
    qr_path = "temp_qr.png"
    qr.save(qr_path)

    c = canvas.Canvas(salida_pdf, pagesize=letter)
    c.drawImage(qr_path, 150, 300, width=300, height=300)
    c.setFont("Helvetica", 12)
    c.drawCentredString(300, 280, "Escanea para verificar autenticidad")
    c.save()

def insertar_pagina_qr(pdf_base: str, pdf_salida: str, qr_url: str):
    """Agrega una página con QR al final del PDF base"""
    pagina_qr = "temp_pagina_qr.pdf"
    generar_pagina_qr(qr_url, pagina_qr)

    base = PdfReader(pdf_base)
    qr = PdfReader(pagina_qr)
    writer = PdfWriter()

    for page in base.pages:
        writer.add_page(page)
    writer.add_page(qr.pages[0])  # Agregar página QR

    with open(pdf_salida, "wb") as f:
        writer.write(f)
