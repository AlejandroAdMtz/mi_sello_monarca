# app.py
import os, json
from flask import (
    Flask,
    request,
    send_file,
    render_template_string,
    abort,
    jsonify,
    url_for
)
from sello_monarca.sello import sell, verify
from sello_monarca.llaves import cargar_llave_privada, cargar_llave_publica
from flask import Flask, request, send_file, render_template_string, abort, jsonify, url_for
import datetime as dt
from zoneinfo import ZoneInfo


PRIVATE_KEY = cargar_llave_privada("keys/private_key.pem", b"secreto")
PUBLIC_KEY  = cargar_llave_publica("keys/public_key.pem")

STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")

@app.route("/sign", methods=["POST"])
def sign_document():
    """
    Recibe multipart/form-data:
    - file: archivo PDF original
    - meta: JSON texto con { uploader, area, ... }
    Devuelve JSON con doc_id, verify_url y el nombre “amigable” de descarga.
    """
    # 1. Validar campos
    if "file" not in request.files or "meta" not in request.form:
        return jsonify({"error": "Falta archivo o metadatos"}), 400

    uploaded_file = request.files["file"]
    original_name = uploaded_file.filename or "documento"
    name_root, ext = os.path.splitext(original_name)
    # Nombre “amigable” para la descarga, pero NO usarlo para almacenamiento
    download_name = f"{name_root}_sellado{ext}"

    # 2. Leer bytes PDF y metadata (JSON) de usuario
    pdf_bytes = uploaded_file.read()
    user_meta = json.loads(request.form["meta"])
    # Guardamos el nombre original dentro de la metadata
    user_meta["original_filename"] = original_name

    # 3. Generar sello usando la función sell()
    #    La función sell() devuelve (pdf_final_bytes, doc_id)
    pdf_sellado_bytes, doc_id = sell(
        pdf_bytes,
        user_meta,
        PRIVATE_KEY,
        base_url=request.url_root + "v/"
    )

    # 4. Guardar el PDF sellado con nombre único = {doc_id}.pdf
    save_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    with open(save_path, "wb") as f:
        f.write(pdf_sellado_bytes)

    # 5. Devolver JSON con campos:
    #    - doc_id         (para verificación)
    #    - verify_url     (para QR o enlace)
    #    - download_name  (nombre bonito para que el usuario descargue)
    return jsonify({
        "doc_id": doc_id,
        "verify_url": request.url_root + f"v/{doc_id}",
        "download_name": download_name
    }), 200

@app.route("/verify", methods=["POST"])
def verify_document():
    """
    Recibe multipart/form-data:
    - file: PDF que incluye metadata + firma + página QR
    Devuelve JSON { valid: true/false, meta: {...} }
    """
    if "file" not in request.files:
        return jsonify({"error": "Falta archivo"}), 400

    pdf_bytes = request.files["file"].read()
    es_valido, meta = verify(pdf_bytes, PUBLIC_KEY)
    return jsonify({"valid": es_valido, "meta": meta})

@app.route("/v/<doc_id>")
def verificacion_publica(doc_id):
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        return "Documento no encontrado", 404

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    es_valido, meta = verify(pdf_bytes, PUBLIC_KEY)

    # Nombre original y download friendly
    original = meta.get("original_filename", doc_id)
    base, ext = os.path.splitext(original)
    download_name = f"{base}_sellado{ext}"

    # ───────── Ajuste simple de fecha (UTC → Monterrey UTC−5 sin depende de zoneinfo) ─────────
    raw_iso = meta.get("uploaded_at", "")
    fecha_amigable = raw_iso  # por defecto, si algo falla
    try:
        # 1) Parsear la cadena ISO con “Z” al final
        dt_utc = dt.datetime.strptime(raw_iso, "%Y-%m-%dT%H:%M:%SZ")
        # 2) Restar 5 horas para pasar a hora de Monterrey (UTC−5)
        dt_mty = dt_utc - dt.timedelta(hours=6)
        # 3) Mapear mes en español
        meses = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]
        dia = dt_mty.day
        mes = meses[dt_mty.month - 1]
        ano = dt_mty.year
        hora = dt_mty.hour
        minuto = dt_mty.minute
        # 4) Formato “30 mayo 2025, 18:50 (MTY)”
        fecha_amigable = f"{dia} {mes} {ano}, {hora:02d}:{minuto:02d} (MTY)"
    except Exception:
        pass



    logo_tec  = url_for('static', filename='logo_tec.png')
    logo_casa = url_for('static', filename='logo_casa_monarca.png')

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>Verificación Casa Monarca</title>
        <style>
          body {{ margin:0; padding:0; background:#f0f2f5; font-family:'Segoe UI',sans-serif; color:#333; }}
          header {{
            background: white;
            padding: 15px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #e0e0e0;
          }}
          header img {{ height: 40px; }}
          header h2 {{ margin:0; font-size:1.2rem; color:#333; letter-spacing:.05em; }}
          main {{
            max-width:800px;
            margin:30px auto;
            background:white;
            border-radius:8px;
            box-shadow:0 4px 12px rgba(0,0,0,0.1);
            overflow:hidden;
          }}
          .content {{ padding:20px; }}
          .status {{
            display:inline-block;
            padding:10px 15px;
            border-radius:4px;
            margin-bottom:20px;
            font-weight:bold;
          }}
          .valido {{ background:#d4edda; color:#155724; }}
          .invalido {{ background:#f8d7da; color:#721c24; }}
          h1 {{ margin-top:0; font-size:1.6rem; }}
          .metadata p {{ margin:6px 0; font-size:.95rem; }}
          iframe {{ width:100%; height:500px; border:none; display:block; margin:20px 0; }}
          .download-btn {{ text-align:center; margin-bottom:20px; }}
          .download-btn a {{ text-decoration:none; }}
          .download-btn button {{
            background: #FF584D;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
            transition: background .2s;
          }}
          .download-btn button:hover {{ background: #e74c3c; }}
          footer {{ text-align:center; padding:15px; font-size:.85rem; color:#777; background:#fafafa; }}
        </style>
      </head>
      <body>
        <header>
          <img src="{logo_tec}" alt="Logo TECNOLOGICO DE MONTERREY">
          <h2>SELLO MONARCA</h2>
          <img src="{logo_casa}" alt="Logo Casa Monarca">
        </header>
        <main>
          <div class="content">
            <h1>Verificación de Documento</h1>
            <div class="status {'valido' if es_valido else 'invalido'}">
              {'✅ VÁLIDO' if es_valido else '❌ NO VÁLIDO'}
            </div>
            <div class="metadata">
              <p><strong>Document ID:</strong> {doc_id}</p>
              <p><strong>Nombre original:</strong> {original}</p>
              <p><strong>Subido por:</strong> {meta.get('uploader','—')}</p>
              <p><strong>Área:</strong> {meta.get('area','—')}</p>
              <p><strong>Fecha:</strong> {fecha_amigable}</p>
            </div>
            <iframe src="/file/{doc_id}"></iframe>
            <div class="download-btn">
              <a href="/download/{doc_id}">
                <button>📥 Descargar "{download_name}"</button>
              </a>
            </div>
          </div>
        </main>
        <footer>
          &copy; {dt.datetime.utcnow().year} CASA MONARCA • TECNOLOGICO DE MONTERREY
        </footer>
      </body>
    </html>
    """
    return html


@app.route("/download/<doc_id>")
def download_pdf(doc_id):
    """
    Sirve el PDF como adjunto forzando el nombre de descarga.
    """
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)

    # Recupera metadatos para obtener el nombre original
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    _, meta = verify(pdf_bytes, PUBLIC_KEY)

    original = meta.get("original_filename", doc_id)
    base, ext = os.path.splitext(original)
    download_name = f"{base}_sellado{ext}"

    # Envía el PDF como attachment con el nombre correcto
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name
    )


@app.route("/file/<doc_id>")
def serve_pdf(doc_id):
    """
    Sirve el PDF salvo con nombre {doc_id}.pdf.
    El navegador lo mostrará o descargará según el link <a download="...">cuyo nombre
    decidimos en /v/<doc_id>.
    """
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)

    # Para que el navegador no cambie el nombre, NO fijamos download_name aquí.
    # El atributo download se envía en <a download="..."> del HTML.
    return send_file(pdf_path, mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
