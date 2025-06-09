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
import datetime as dt
from zoneinfo import ZoneInfo

from hashlib import sha256
from sello_monarca.sello import verify, META_KEY
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv(override=True)

# Carga de llaves desde .env
PRIVATE_KEY_ENV = os.getenv("PRIVATE_KEY_PEM")
PUBLIC_KEY_ENV  = os.getenv("PUBLIC_KEY_PEM")

from sello_monarca.llaves import cargar_llave_privada_desde_env,  cargar_llave_publica_desde_env

PRIVATE_KEY = cargar_llave_privada_desde_env(PRIVATE_KEY_ENV, password=b"secreto")
PUBLIC_KEY  = cargar_llave_publica_desde_env(PUBLIC_KEY_ENV)

# Resto de variables
SP_SITE      = os.getenv("SP_SITE")
SP_DOC_LIB   = os.getenv("SP_DOC_LIB")
SP_LIST      = os.getenv("SP_LIST")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5000")
TZ           = os.getenv("TZ", "America/Monterrey")
SAVE_LOCAL = os.getenv("SAVE_LOCAL", "0") == "1" # Si es 1, guarda PDFs en disco local

# Crear carpeta local para PDFs
STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200, {"Content-Type": "text/plain"}

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
        "download_url": request.url_root + f"download/{doc_id}",
        "download_name": download_name
    }), 200

import base64, re

@app.route("/sign-json", methods=["POST"])
def sign_json():
    if not request.is_json:
        return jsonify({"error": "Solo se acepta JSON"}), 400
    
    data = request.get_json()

    # Campos requeridos
    try:
        file_b64   = data["file_base64"]
        uploader   = data["uploader"]
        area       = data["area"]
        orig_name  = data["original_filename"]
    except KeyError as e:
        return jsonify({"error": f"Falta campo {e}"}), 400


    # 1) Decodifica el PDF
    try:
        # a) quita prefijos tipo "data:application/pdf;base64,"
        if file_b64.startswith("data:"):
            file_b64 = file_b64.split(",", 1)[1]

        # b) elimina blancos y saltos (\s incluye \r \n \t y espacios)
        file_b64_clean = re.sub(r"\s+", "", file_b64)

        # c) decodifica; validate=True obliga a que sean caracteres base64 válidos
        pdf_bytes = base64.b64decode(file_b64_clean, validate=True)

    except Exception as e:
        print("B64 error:", e)          # aparecerá en los logs de Render
        return jsonify({"error": "base64 inválido"}), 400

    user_meta = {
        "uploader": uploader,
        "area": area,
        "original_filename": orig_name
    }

    # 2) Firma
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

    # 3) Cabezeras para el Flow
    headers = {
        "Content-Type":       "application/pdf",          #  ← NUEVO
        "X-Doc-ID":            doc_id,
        "X-Verify-URL":        request.url_root + f"v/{doc_id}",
        "X-Uploader":          uploader,
        "X-Area":              area,
        "X-Original-Filename": orig_name,
        "X-Uploaded-At":       dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "X-Download-Name":     f"{os.path.splitext(orig_name)[0]}_sellado.pdf",
        "Content-Disposition": f'attachment; filename="{doc_id}.pdf"'
    }

    return pdf_sellado_bytes, 200, headers


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
    """
    Muestra una página profesional y limpia para verificar un PDF sellado.
    - Oculta la firma, muestra solo los campos relevantes.
    - Logos con márgenes, tarjeta blanca centrada.
    - Fecha en hora de Monterrey (UTC-5).
    """
    # 1) Ruta de disco al PDF por doc_id
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        return "Documento no encontrado", 404

    # 2) Leer el PDF y extraer metadata + verificación
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    es_valido, meta = verify(pdf_bytes, PUBLIC_KEY)

    # 3) Montar el nombre original y generar nombre de descarga si lo necesitas
    original = meta.get("original_filename", doc_id)
    base, ext = os.path.splitext(original)
    download_name = f"{base}_sellado{ext}"

    # 4) Formatear la fecha en hora de Monterrey (UTC-5), mes en español
    raw_iso = meta.get("uploaded_at", "")
    fecha_amigable = raw_iso  # fallback si algo falla
    try:
        # Parseamos la cadena ISO "2025-05-30T23:12:35Z"
        dt_utc = dt.datetime.strptime(raw_iso, "%Y-%m-%dT%H:%M:%SZ")
        # Restamos 5 horas para zona Monterrey
        dt_mty = dt_utc - timedelta(hours=6)
        meses = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]
        dia = dt_mty.day
        mes = meses[dt_mty.month - 1]
        ano = dt_mty.year
        hora = dt_mty.hour
        minuto = dt_mty.minute
        fecha_amigable = f"{dia} {mes} {ano}, {hora:02d}:{minuto:02d} (MTY)"
    except Exception:
        pass

    # 5) Rutas a los logos (debes tener estos archivos en static/)
    logo_tec  = url_for('static', filename='logo_tec.png')
    logo_casa = url_for('static', filename='logo_casa_monarca.png')

    # 6) Construir solo los metadatos que queremos mostrar (sin signature ni verify_url)
    metadatos_mostrar = {
        "Área": meta.get("area", "—"),
        "Document ID": meta.get("id", doc_id),
        "Nombre original": meta.get("original_filename", "—"),
        "Subido por": meta.get("uploader", "—"),
        "Fecha": fecha_amigable
    }

    # 7) HTML + CSS inline: diseño limpio, tarjeta centrada
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>Verificación Casa Monarca</title>
        <style>
          * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }}
          html, body {{
            background: #f0f2f5;
            font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
            color: #2c2c2c;
            line-height: 1.5;
          }}
          a {{
            text-decoration: none;
            color: inherit;
          }}

          /* HEADER CON LOGOS EN ESQUINAS PARA DESKTOP */
          header {{
            background: white;
            padding: 15px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #e0e0e0;
            position: relative;
          }}
          .logo-tec {{
            height: 55px;  /* Más grande para desktop */
          }}
          .logo-casa {{
            height: 55px;  /* Más grande para desktop */
          }}
          header h2 {{
            font-size: 1.4rem;
            color: #1a1a1a;
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
          }}

          main {{
            display: flex;
            justify-content: center;
            margin: 40px 20px;
            padding: 0 10px;
          }}
          .tarjeta {{
            background: white;
            width: 100%;
            max-width: 800px;
            border-radius: 8px;
            box-shadow: 0 3px 15px rgba(0,0,0,0.1);
            overflow: hidden;
          }}
          .tarjeta .contenido {{
            padding: 30px;
          }}

          .tarjeta h1 {{
            font-size: 1.8rem;
            margin-bottom: 25px;
            text-align: center;
            color: #00539c;
          }}
          .estado {{
            display: block;
            text-align: center;
            margin: 0 auto 25px auto;
            padding: 12px 20px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 1.2rem;
            max-width: 300px;
          }}
          .estado.valido {{
            background: #d4edda;
            color: #155724;
            border: 2px solid #155724;
          }}
          .estado.invalido {{
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #721c24;
          }}

          .tabla-meta {{
            width: 100%;
            border-collapse: collapse;
            margin: 30px 0;
            font-size: 1.1rem;
          }}
          .tabla-meta th, .tabla-meta td {{
            border: 1px solid #d0d0d0;
            padding: 15px 20px;
            text-align: left;
          }}
          .tabla-meta th {{
            background: #00539c;
            color: white;
            font-weight: 500;
            width: 30%;
          }}
          .tabla-meta td {{
            background: #fafafa;
          }}

          .visor-pdf {{
            width: 100%;
            height: 550px;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin: 30px 0;
          }}

          .boton-descarga {{
            display: flex;
            justify-content: center;
            margin: 30px 0;
          }}
          .boton-descarga a {{
            background: #FF584D;
            color: white;
            padding: 15px 40px;
            border-radius: 6px;
            font-size: 1.2rem;
            font-weight: bold;
            transition: background 0.3s;
            text-align: center;
            box-shadow: 0 4px 8px rgba(255, 88, 77, 0.3);
          }}
          .boton-descarga a:hover {{
            background: #e74c3c;
            transform: translateY(-2px);
          }}

          footer {{
            text-align: center;
            padding: 20px;
            font-size: 0.9rem;
            color: #666;
            background: #fafafa;
            border-top: 1px solid #eee;
          }}

          /* MEDIA QUERIES PARA MÓVILES */
          @media (max-width: 768px) {{
            header {{
              flex-direction: column;
              padding: 15px;
              text-align: center;
            }}
            .logo-tec, .logo-casa {{
              height: 45px;
              margin: 5px 0;
            }}
            header h2 {{
              position: static;
              transform: none;
              margin: 10px 0;
              font-size: 1.3rem;
              width: 100%;
            }}
            .tarjeta .contenido {{
              padding: 20px;
            }}
            .tarjeta h1 {{
              font-size: 1.4rem;
            }}
            .estado {{
              font-size: 1rem;
              padding: 10px;
            }}
            .tabla-meta th, 
            .tabla-meta td {{
              padding: 10px 12px;
              font-size: 0.95rem;
            }}
            .visor-pdf {{
              height: 350px;
            }}
            .boton-descarga a {{
              padding: 12px 25px;
              font-size: 1.1rem;
              width: 100%;
              max-width: 300px;
            }}
          }}

          @media (max-width: 480px) {{
            .tarjeta .contenido {{
              padding: 15px;
            }}
            .tarjeta h1 {{
              font-size: 1.25rem;
            }}
            .estado {{
              font-size: 0.95rem;
            }}
            .visor-pdf {{
              height: 280px;
            }}
            .boton-descarga a {{
              font-size: 1rem;
            }}
          }}
        </style>
      </head>
      <body>
        <header>
          <img class="logo-tec" src="{logo_tec}" alt="Tecnológico de Monterrey" />
          <h2>SELLO MONARCA</h2>
          <img class="logo-casa" src="{logo_casa}" alt="Casa Monarca" />
        </header>

        <main>
          <div class="tarjeta">
            <div class="contenido">
              <h1>Verificación de Documento</h1>
              <div class="estado {'valido' if es_valido else 'invalido'}">
                {'✅ DOCUMENTO VÁLIDO' if es_valido else '❌ DOCUMENTO NO VÁLIDO'}
              </div>

              <table class="tabla-meta">
                <tbody>
                  {"".join([
                    f"<tr><th>{campo}</th><td>{valor}</td></tr>"
                    for campo, valor in metadatos_mostrar.items()
                  ])}
                </tbody>
              </table>

              <iframe class="visor-pdf" src="/file/{doc_id}"></iframe>

              <div class="boton-descarga">
                <a href="/download/{doc_id}" download="{download_name}">
                  📥 DESCARGAR DOCUMENTO
                </a>
              </div>
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


@app.route("/file/<doc_id>")
def serve_pdf(doc_id):
    """
    Sirve el PDF (sin forzar nombre). El nombre correcto para descarga
    se manejará en /download/<doc_id>.
    """
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)
    return send_file(pdf_path, mimetype="application/pdf")

@app.route("/download/<doc_id>")
def download_pdf(doc_id):
    """
    Envía el PDF forzando la descarga con nombre amigable.
    """
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)

    # Leer los metadatos para obtener el nombre original
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    _, meta = verify(pdf_bytes, PUBLIC_KEY)

    original = meta.get("original_filename", doc_id)
    base, ext = os.path.splitext(original)
    download_name = f"{base}_sellado{ext}"

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name
    )

@app.route("/verify-ui")
def verify_ui():
    """
    Página Drag & Drop (o clic) para verificar un PDF sellado.
    - Permite arrastrar el archivo o hacer clic para abrir selector.
    - Muestra ✅ VÁLIDO o ❌ NO VÁLIDO con tabla de metadatos.
    """
    # URL de tu endpoint /verify
    verify_api_url = request.url_root.rstrip("/") + "/verify"

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>Verificar PDF Sellado</title>
        <style>
          * {{ 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
          }}
          body {{
            background: #f0f2f5;
            font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
            color: #2c2c2c;
            line-height: 1.5;
          }}

          header {{
            background: white;
            padding: 15px 20px;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            gap: 15px;
            border-bottom: 1px solid #e0e0e0;
          }}
          .logo-container {{
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 15px;
            width: 100%;
          }}
          header img {{
            height: 40px;
            max-width: 100px;
            object-fit: contain;
          }}
          header h2 {{
            font-size: 1.2rem;
            color: #1a1a1a;
            text-align: center;
            width: 100%;
          }}

          main {{
            display: flex;
            justify-content: center;
            margin: 30px 15px;
          }}
          .tarjeta {{
            background: white;
            width: 100%;
            max-width: 700px;
            border-radius: 8px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            overflow: hidden;
          }}
          .tarjeta .contenido {{
            padding: 20px;
          }}

          .tarjeta h1 {{
            font-size: 1.4rem;
            margin-bottom: 10px;
            text-align: center;
          }}
          .subtitulo {{
            font-size: 1rem;
            color: #555;
            margin-bottom: 20px;
            text-align: center;
          }}

          #dropZone {{
            height: 180px;
            border: 3px dashed #ccc;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #777;
            font-size: 1.1rem;
            transition: all 0.3s ease;
            margin-bottom: 20px;
            cursor: pointer;
            user-select: none;
            background: #fafafa;
            text-align: center;
            padding: 15px;
          }}
          #dropZone.dragover {{
            border-color: #00539c;
            color: #00539c;
            background: #e8f0fe;
          }}

          input[type="file"] {{
            display: none;
          }}

          .estado {{
            display: inline-block;
            padding: 10px 15px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 1rem;
            margin-bottom: 15px;
            width: 100%;
            text-align: center;
          }}
          .valido {{
            background: #d4edda;
            color: #155724;
          }}
          .invalido {{
            background: #f8d7da;
            color: #721c24;
          }}

          .tabla-meta-container {{
            overflow-x: auto;
            margin: 20px 0;
            -webkit-overflow-scrolling: touch;
          }}
          .tabla-meta {{
            width: 100%;
            border-collapse: collapse;
          }}
          .tabla-meta th, .tabla-meta td {{
            border: 1px solid #d0d0d0;
            padding: 10px 12px;
            text-align: left;
            min-width: 120px;
          }}
          .tabla-meta th {{
            background: #00539c;
            color: white;
            font-weight: 500;
          }}
          .tabla-meta td {{ 
            background: #fafafa; 
            word-break: break-word;
          }}

          footer {{
            text-align: center;
            padding: 15px 10px;
            font-size: 0.8rem;
            color: #666;
            background: #fafafa;
            margin-top: 30px;
          }}

          /* Media queries para móviles */
          @media (max-width: 768px) {{
            header {{
              padding: 12px 15px;
            }}
            header h2 {{
              font-size: 1.1rem;
            }}
            .tarjeta .contenido {{
              padding: 15px;
            }}
            .tarjeta h1 {{
              font-size: 1.25rem;
            }}
            .subtitulo {{
              font-size: 0.9rem;
            }}
            #dropZone {{
              height: 150px;
              font-size: 1rem;
              padding: 10px;
            }}
            .estado {{
              font-size: 0.9rem;
              padding: 8px 10px;
            }}
            .tabla-meta th, 
            .tabla-meta td {{
              padding: 8px 10px;
              font-size: 0.9rem;
            }}
          }}

          @media (max-width: 480px) {{
            .logo-container {{
              flex-direction: column;
              align-items: center;
              gap: 8px;
            }}
            #dropZone {{
              height: 120px;
              font-size: 0.95rem;
            }}
          }}
        </style>
      </head>

      <body>
        <header>
          <div class="logo-container">
            <img src="{url_for('static', filename='logo_tec.png')}" alt="Logo TECNOLOGICO DE MONTERREY" />
            <img src="{url_for('static', filename='logo_casa_monarca.png')}" alt="Logo CASA MONARCA" />
          </div>
          <h2>SELLO MONARCA</h2>
        </header>

        <main>
          <div class="tarjeta">
            <div class="contenido">
              <h1>Arrastra o haz clic para subir tu PDF</h1>
              <p class="subtitulo">Sólo archivos .pdf válidos</p>

              <div id="dropZone">
                📁 Selecciona o arrastra aquí tu PDF
              </div>
              <input type="file" id="fileInput" accept="application/pdf" />
              <div id="result"></div>
            </div>
          </div>
        </main>

        <footer>
          &copy; {dt.datetime.utcnow().year} CASA MONARCA • TECNOLOGICO DE MONTERREY
        </footer>

        <script>
          // ... (mismo javascript previo)
        </script>
      </body>
    </html>
    """
    return html


if __name__ == "__main__":
  port = int(os.getenv("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
