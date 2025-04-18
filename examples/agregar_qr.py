from sello_monarca.qr_handler import insertar_pagina_qr

pdf_entrada = "examples/documento_sellado.pdf"
pdf_salida = "examples/documento_con_qr.pdf"
url_qr = "https://casamonarca.org.mx/"

insertar_pagina_qr(pdf_entrada, pdf_salida, url_qr)
print("✅ Código QR agregado exitosamente al PDF.")
