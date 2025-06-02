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

@app.route("/sign-binary", methods=["POST"])
def sign_binary():
    if "file" not in request.files or "meta" not in request.form:
        return jsonify({"error": "Falta archivo o metadatos"}), 400

    pdf_bytes  = request.files["file"].read()
    user_meta  = json.loads(request.form["meta"])

    # 1. Sellar (sin guardar a disco)
    pdf_sellado_bytes, doc_id = sell(
        pdf_bytes,
        user_meta,
        PRIVATE_KEY,
        base_url=request.url_root + "v/"
    )

    # 2. Construir headers que el Flow llenará en SharePoint
    headers = {
        # nombre “bonito” que guardaremos como archivo
        "X-Download-Name": f"{os.path.splitext(user_meta['original_filename'])[0]}_sellado.pdf",
        # ID interno del documento
        "X-Doc-ID":        doc_id,
        # URL pública de verificación (para la columna VerifyURL)
        "X-Verify-URL":    request.url_root + f"v/{doc_id}",
        # Fecha ISO (para UploadedAt)
        "X-Uploaded-At":   dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Propiedades visibles
        "X-Uploader":      user_meta["uploader"],
        "X-Area":          user_meta["area"],
        "X-Original-Filename": user_meta["original_filename"],
        # Content-Disposition para que cURL/Flow sepa el nombre sugerido
        "Content-Disposition": f'attachment; filename="{doc_id}.pdf"'
    }

    # 3. Responder el PDF sellado como binario
    return pdf_sellado_bytes, 200, headers


import base64

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
        pdf_bytes = base64.b64decode(file_b64)
    except Exception:
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

    # 3) Cabezeras para el Flow
    headers = {
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

@app.route("/sign-binary-body", methods=["POST"])
def sign_binary_body():
    # ← 1) bytes puros del PDF
    pdf_bytes = request.data
    if not pdf_bytes.startswith(b"%PDF"):
        return jsonify({"error": "El body no parece un PDF"}), 400

    # ← 2) metadatos desde headers
    uploader = request.headers.get("X-Uploader", "—")
    area     = request.headers.get("X-Area", "—")
    orig_fn  = request.headers.get("X-Original-Filename", "documento.pdf")

    user_meta = {
        "uploader": uploader,
        "area": area,
        "original_filename": orig_fn
    }

    # 3) Firmar sin tocar disco
    pdf_sellado_bytes, doc_id = sell(
        pdf_bytes,
        user_meta,
        PRIVATE_KEY,
        base_url=request.url_root + "v/"
    )

    # 4) Headers de respuesta
    headers = {
        "X-Doc-ID":            doc_id,
        "X-Verify-URL":        request.url_root + f"v/{doc_id}",
        "X-Uploader":          uploader,
        "X-Area":              area,
        "X-Original-Filename": orig_fn,
        "X-Uploaded-At":       dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "X-Download-Name":     f"{os.path.splitext(orig_fn)[0]}_sellado.pdf",
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
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Verificación Casa Monarca</title>
        <style>
          * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }}
          html, body {{
            background: #f0f2f5;
            font-family: 'Segoe UI', sans-serif;
            color: #2c2c2c;
          }}
          a {{
            text-decoration: none;
            color: inherit;
          }}

          header {{
            background: white;
            padding: 15px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #e0e0e0;
            flex-wrap: wrap;
          }}
          header img {{
            height: 45px;
            max-width: 100px;
            object-fit: contain;
            margin: 5px 10px;
          }}
          header h2 {{
            font-size: 1.3rem;
            color: #1a1a1a;
            letter-spacing: 0.05em;
            text-align: center;
            flex-grow: 1;
          }}

          main {{
            display: flex;
            justify-content: center;
            margin: 40px 20px;
            width: 100%;
            padding: 0 10px;
          }}
          .tarjeta {{
            background: white;
            width: 100%;
            max-width: 700px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            overflow: hidden;
          }}
          .tarjeta .contenido {{
            padding: 25px 30px;
          }}

          .tarjeta h1 {{
            font-size: 1.6rem;
            margin-bottom: 25px;
            text-align: center;
          }}
          .estado {{
            display: block;
            text-align: center;
            margin: 0 auto 20px auto;
            padding: 10px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 1rem;
          }}
          .estado.valido {{
            background: #d4edda;
            color: #155724;
          }}
          .estado.invalido {{
            background: #f8d7da;
            color: #721c24;
          }}

          .tabla-meta {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0 30px;
            display: block;
            overflow-x: auto;
            white-space: nowrap;
          }}
          .tabla-meta th, .tabla-meta td {{
            border: 1px solid #d0d0d0;
            padding: 10px 12px;
            text-align: left;
          }}
          .tabla-meta th {{
            background: #00539c;
            color: white;
            font-weight: normal;
            width: 35%;
          }}
          .tabla-meta td {{
            background: #fafafa;
          }}

          .visor-pdf {{
            width: 100%;
            max-width: 100%;
            height: 500px;
            border: 1px solid #ccc;
            border-radius: 4px;
            margin-bottom: 25px;
          }}

          .boton-descarga {{
            display: flex;
            justify-content: center;
            margin-bottom: 20px;
          }}
          .boton-descarga a {{
            background: #FF584D;
            color: white;
            padding: 12px 28px;
            border-radius: 4px;
            font-size: 1rem;
            font-weight: bold;
            transition: background 0.2s;
            text-align: center;
          }}
          .boton-descarga a:hover {{
            background: #e74c3c;
          }}

          footer {{
            text-align: center;
            padding: 15px 0;
            font-size: 0.85rem;
            color: #666;
            background: #fafafa;
          }}

          @media (max-width: 600px) {{
            html, body {{
              overflow-x: hidden;
              font-size: 0.95rem;
            }}
            header {{
              flex-direction: column;
              align-items: center;
              gap: 5px;
              padding: 20px 10px;
            }}
            header img {{
              height: 40px;
            }}
            header h2 {{
              font-size: 1.1rem;
              margin: 5px 0;
            }}
            .tarjeta .contenido {{
              padding: 20px 15px;
              font-size: 0.95rem;
            }}
            .tarjeta h1 {{
              font-size: 1.3rem;
            }}
            .tabla-meta th,
            .tabla-meta td {{
              font-size: 0.85rem;
            }}
            .boton-descarga a {{
              width: 100%;
              padding: 12px;
            }}
          }}
        </style>
      </head>
      <body>
        <header>
          <img src="{logo_tec}" alt="Logo TECNOLOGICO DE MONTERREY" />
          <h2>SELLO MONARCA</h2>
          <img src="{logo_casa}" alt="Logo CASA MONARCA" />
        </header>

        <main>
          <div class="tarjeta">
            <div class="contenido">
              <h1>Verificación de Documento</h1>
              <div class="estado {'valido' if es_valido else 'invalido'}">
                {'✅ VÁLIDO' if es_valido else '❌ NO VÁLIDO'}
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
                  📥 Descargar "{download_name}"
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
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Verificar PDF Sellado</title>
        <style>
          /* Reset básico */
          * {{ margin: 0; padding: 0; box-sizing: border-box; }}
          body {{
            background: #f0f2f5;
            font-family: 'Segoe UI', sans-serif;
            color: #2c2c2c;
          }}

          /* Header blanco */
          header {{
            background: white;
            padding: 15px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #e0e0e0;
          }}
          header img {{
            height: 45px;
            margin: 0 10px;
          }}
          header h2 {{
            font-size: 1.3rem;
            color: #1a1a1a;
            letter-spacing: 0.05em;
          }}

          /* Contenedor principal centrado */
          main {{
            display: flex;
            justify-content: center;
            margin: 40px 20px;
          }}
          .tarjeta {{
            background: white;
            width: 100%;
            max-width: 700px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            overflow: hidden;
          }}
          .tarjeta .contenido {{
            padding: 25px 30px;
          }}

          /* Título y subtítulo */
          .tarjeta h1 {{
            font-size: 1.6rem;
            margin-bottom: 5px;
            text-align: center;
          }}
          .tarjeta p.subtitulo {{
            font-size: 1rem;
            color: #555;
            margin-bottom: 20px;
            text-align: center;
          }}

          /* Drop Zone con estado híbrido */
          #dropZone {{
            height: 200px;
            border: 3px dashed #ccc;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #777;
            font-size: 1.1rem;
            transition: border-color 0.2s, color 0.2s, background 0.2s;
            margin-bottom: 25px;
            cursor: pointer;
            user-select: none;
            background: #fafafa;
          }}
          #dropZone.dragover {{
            border-color: #00539c;
            color: #00539c;
            background: #e8f0fe;
          }}

          /* Input file oculto (se dispara al hacer clic en el dropZone) */
          input[type="file"] {{
            display: none;
          }}

          /* Estado de validación */
          .estado {{
            display: inline-block;
            padding: 10px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 1rem;
            margin-bottom: 20px;
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

          /* Tabla de metadatos */
          .tabla-meta {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0 30px;
          }}
          .tabla-meta th, .tabla-meta td {{
            border: 1px solid #d0d0d0;
            padding: 10px 12px;
            text-align: left;
          }}
          .tabla-meta th {{
            background: #00539c;
            color: white;
            font-weight: normal;
            width: 35%;
          }}
          .tabla-meta td {{ background: #fafafa; }}

          /* Pie de página */
          footer {{
            text-align: center;
            padding: 15px 0;
            font-size: 0.85rem;
            color: #666;
            background: #fafafa;
            margin-top: 40px;
          }}
        </style>
      </head>

      <body>
        <!-- Header con logos -->
        <header>
          <img src="{url_for('static', filename='logo_tec.png')}" alt="Logo TECNOLOGICO DE MONTERREY" />
          <h2>SELLO MONARCA</h2>
          <img src="{url_for('static', filename='logo_casa_monarca.png')}" alt="Logo CASA MONARCA" />
        </header>

        <!-- Contenedor principal -->
        <main>
          <div class="tarjeta">
            <div class="contenido">
              <h1>Arrastra o haz clic para subir tu PDF</h1>
              <p class="subtitulo">Sólo archivos .pdf válidos</p>

              <!-- Drop Zone híbrido -->
              <div id="dropZone">
                📁 Selecciona o arrastra aquí tu PDF
              </div>

              <!-- Input file oculto -->
              <input type="file" id="fileInput" accept="application/pdf" />

              <!-- Resultado (estado + metadatos) -->
              <div id="result"></div>
            </div>
          </div>
        </main>

        <!-- Pie de página -->
        <footer>
          &copy; {dt.datetime.utcnow().year} CASA MONARCA • TECNOLOGICO DE MONTERREY
        </footer>

        <script>
          const dropZone = document.getElementById('dropZone');
          const resultDiv = document.getElementById('result');
          const fileInput = document.getElementById('fileInput');
          const apiURL = "{verify_api_url}";

          // Función que maneja un archivo PDF: lo envía a /verify y muestra el resultado
          async function handleFile(file) {{
            // Validar tipo
            if (!file || file.type !== "application/pdf") {{
              resultDiv.innerHTML = "<p style='color:red; font-weight:bold;'>Por favor, sube un archivo PDF válido.</p>";
              return;
            }}

            resultDiv.innerHTML = "<p>Verificando el documento…</p>";

            const formData = new FormData();
            formData.append("file", file);

            try {{
              const resp = await fetch(apiURL, {{
                method: "POST",
                body: formData
              }});
              const data = await resp.json();

              if (data.valid) {{
                // Construir tabla de metadatos formateada
                let html = "<div class='estado valido'>✅ VÁLIDO</div>";
                html += "<table class='tabla-meta'><tbody>";

                // Los campos que mostraremos
                const campos = {{
                  "Área": data.meta.area || "—",
                  "Document ID": data.meta.id || "—",
                  "Nombre original": data.meta.original_filename || "—",
                  "Subido por": data.meta.uploader || "—",
                  // Formatear fecha UTC->MTY
                  "Fecha": (() => {{
                    const raw = data.meta.uploaded_at || "";
                    try {{
                      const dtUtc = new Date(raw);
                      dtUtc.setHours(dtUtc.getHours());
                      const meses = [
                        "enero","febrero","marzo","abril","mayo","junio",
                        "julio","agosto","septiembre","octubre","noviembre","diciembre"
                      ];
                      const d = dtUtc.getDate();
                      const m = meses[dtUtc.getMonth()];
                      const a = dtUtc.getFullYear();
                      const h = String(dtUtc.getHours()).padStart(2, "0");
                      const mi = String(dtUtc.getMinutes()).padStart(2, "0");
                      return `${{d}} ${{m}} ${{a}}, ${{h}}:${{mi}} (MTY)`;
                    }} catch {{
                      return raw;
                    }}
                  }})()
                }};

                for (const [k,v] of Object.entries(campos)) {{
                  html += `<tr><th>${{k}}</th><td>${{v}}</td></tr>`;
                }}
                html += "</tbody></table>";
                resultDiv.innerHTML = html;
              }} else {{
                resultDiv.innerHTML = "<div class='estado invalido'>❌ NO VÁLIDO</div>";
              }}
            }} catch (err) {{
              console.error(err);
              resultDiv.innerHTML = "<p style='color:red; font-weight:bold;'>Error al conectar con el servidor.</p>";
            }}
          }}

          // Drag & drop: cambiar estilo al pasar archivo
          dropZone.addEventListener('dragover', e => {{
            e.preventDefault();
            dropZone.classList.add('dragover');
          }});
          dropZone.addEventListener('dragleave', () => {{
            dropZone.classList.remove('dragover');
          }});
          dropZone.addEventListener('drop', e => {{
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            handleFile(file);
          }});

          // Al hacer clic en dropZone, abre fileInput
          dropZone.addEventListener('click', () => {{
            fileInput.click();
          }});

          // Cuando seleccionan archivo con fileInput
          fileInput.addEventListener('change', () => {{
            const file = fileInput.files[0];
            handleFile(file);
          }});
        </script>
      </body>
    </html>
    """
    return html




if __name__ == "__main__":
  port = int(os.getenv("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
