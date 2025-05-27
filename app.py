from flask import Flask, request, send_file, render_template_string, abort, jsonify
import os, uuid, json

from sello_monarca.sello import sell, verify
from sello_monarca.llaves import cargar_llave_privada, cargar_llave_publica

# Configura rutas de llaves
PRIVATE_KEY = cargar_llave_privada("keys/private_key.pem", b"secreto")
PUBLIC_KEY  = cargar_llave_publica("keys/public_key.pem")

# Directorio donde se guardan los PDFs sellados
STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

app = Flask(__name__)

@app.route("/sign", methods=["POST"])
def sign_document():
    # Recibe archivo y metadatos JSON
    if 'file' not in request.files or 'meta' not in request.form:
        return jsonify({"error": "Falta archivo o metadatos"}), 400

    file = request.files["file"]
    meta = json.loads(request.form["meta"])
    pdf_bytes = file.read()

    pdf_sellado, doc_id = sell(pdf_bytes, meta, PRIVATE_KEY, base_url=request.url_root + "v/")
    # Guarda el PDF sellado con su doc_id
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_sellado)

    verify_url = f"{request.url_root}v/{doc_id}"
    return jsonify({
        "doc_id": doc_id,
        "verify_url": verify_url
    }), 200

@app.route("/verify", methods=["POST"])
def verify_document():
    if 'file' not in request.files:
        return jsonify({"error": "Falta archivo"}), 400
    file = request.files["file"]
    pdf_bytes = file.read()
    valido, meta = verify(pdf_bytes, PUBLIC_KEY)
    return jsonify({
        "valid": valido,
        "meta": meta
    })

@app.route("/v/<doc_id>")
def verificacion_publica(doc_id):
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        return "Documento no encontrado", 404
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    valido, meta = verify(pdf_bytes, PUBLIC_KEY)

    # Página HTML minimalista y elegante
    return render_template_string("""
    <html>
    <head>
        <title>Verificación Documento Casa Monarca</title>
    </head>
    <body>
        <h2>Documento: {{ doc_id }}</h2>
        <p style="color:{{ 'green' if valido else 'red' }};">
            <strong>{{ '✅ Válido' if valido else '❌ No válido' }}</strong>
        </p>
        <p>Subido por: {{ meta.get('uploader', '—') }}</p>
        <p>Área: {{ meta.get('area', '—') }}</p>
        <p>Fecha: {{ meta.get('uploaded_at', '—') }}</p>
        <iframe src="/file/{{ doc_id }}" width="100%" height="600px"></iframe>
    </body>
    </html>
    """, doc_id=doc_id, valido=valido, meta=meta)

@app.route("/file/<doc_id>")
def serve_pdf(doc_id):
    pdf_path = os.path.join(STORAGE_DIR, f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)
    return send_file(pdf_path, download_name=f"{doc_id}.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
