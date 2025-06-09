# sello_monarca/qr_handler.py
from io import BytesIO
import os, qrcode, datetime
from urllib.parse import urlparse, parse_qs

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import cm
from reportlab.lib import colors
from flask import current_app


# Ajusta el nombre o la ruta si tu archivo se llama distinto
# dentro de la función que genera el PDF (o justo antes)



def generar_pagina_qr_bytes(url: str) -> bytes:
    """
    Genera una portada PDF que contiene:
      – Logotipo de Casa Monarca
      – Título “Sello Monarca”
      – Subtítulo “Verificación de documentos”
      – Código QR (link clicable y texto)
      – Metadatos ligeros (ID y fecha)
    Devuelve los bytes del PDF para que insertes la página al final
    con tu función insertar_pagina_qr().
    """
    # ---------- Extrae metadatos -------
    doc_id = parse_qs(urlparse(url).query).get("id", [""])[0]
    fecha  = datetime.datetime.utcnow().strftime("%d-%b-%Y")

    # ---------- QR ----------
    qr_buf = BytesIO()
    qrcode.make(url).save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_img = ImageReader(qr_buf)

    # ---------- Logo ----------
    logo_path = os.path.join(current_app.static_folder, "logo_casa_monarca.png")
    logo_img  = ImageReader(logo_path)
    lw_pt, lh_pt = logo_img.getSize()
    max_logo = 4 * cm                        # límite en 4 cm sin deformar
    scale = min(max_logo / lw_pt, max_logo / lh_pt, 1)
    lw, lh = lw_pt * scale, lh_pt * scale

    # ---------- Página ----------
    buf = BytesIO()
    c   = canvas.Canvas(buf, pagesize=letter)
    W, H = letter

    # 1) Encabezado
    top_y = H - 2 * cm
    # Logo
    c.drawImage(logo_img, 2 * cm, top_y - lh, lw, lh, mask="auto")
    # Título “Sello Monarca”
    c.setFont("Helvetica-Bold", 24)
    c.drawString(2 * cm + lw + 3 * cm, top_y - (lh / 2) - 10, "Sello Monarca")
    # Línea divisoria
    c.setStrokeColor(colors.grey)
    c.line(2 * cm, top_y - lh - 0.4 * cm, W - 2 * cm, top_y - lh - 0.4 * cm)
    # Sub-título
    c.setFont("Helvetica-Oblique", 13)
    c.setFillColor(colors.darkgray)
    c.drawString(2 * cm, top_y - lh - 1.1 * cm, "Verificación de documentos")
    c.setFillColor(colors.black)

    # 2) QR centrado
    qr_side = 8 * cm
    qr_y = H / 2 - qr_side / 2 + 2.5 * cm    # un poco más arriba para compactar
    c.drawImage(
        qr_img,
        (W - qr_side) / 2,
        qr_y,
        qr_side,
        qr_side,
        mask="auto"
    )

    # 3) Mensaje principal
    ty = qr_y - 1.2 * cm
    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, ty,
        "Este PDF está firmado digitalmente por Casa Monarca.")
    c.drawCentredString(W / 2, ty - 0.45 * cm,
        "Escanea el código QR o visita la URL para confirmar su autenticidad:")

    # URL clicable
    link_y = ty - 1.1 * cm
    c.setFillColor(colors.blue)
    c.drawCentredString(W / 2, link_y, url)
    c.linkURL(url, (W * 0.1, link_y - 0.2 * cm, W * 0.9, link_y + 0.3 * cm), relative=0)
    c.setFillColor(colors.black)

    # 4) Metadatos gris
    meta_y = 2 * cm
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    if doc_id:
        c.drawString(2 * cm, meta_y, f"ID del documento: {doc_id}")
    c.drawString(W - 2 * cm - 130, meta_y, f"Emitido: {fecha}")
    c.setFillColor(colors.black)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


# ------------------ Ayudante opcional (sin cambios) ------------------
def generar_pagina_qr(url: str, path: str) -> None:
    """Guarda en 'path' el PDF generado."""
    with open(path, "wb") as f:
        f.write(generar_pagina_qr_bytes(url))
