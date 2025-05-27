# sello_monarca/sello.py
from __future__ import annotations
from io import BytesIO
import json, uuid, base64, datetime as dt
from hashlib import sha256
from typing import Tuple, Dict, Any

from PyPDF2 import PdfReader, PdfWriter, generic
from sello_monarca.utils import firmar_hash, verificar_firma
from sello_monarca.qr_handler import generar_pagina_qr_bytes

META_KEY = "/CM_META"
SIGN_PLACEHOLDER = "FIRMA_PENDIENTE"

def _utc_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _merge_metadata(base_meta: dict, extra: dict) -> dict:
    meta = {}
    for k, v in base_meta.items():
        meta[generic.NameObject(str(k))] = generic.create_string_object(str(v))
    for k, v in extra.items():
        meta[generic.NameObject(k)] = generic.create_string_object(str(v))
    return meta

def _embed_meta(pdf_bytes: bytes, json_meta: str) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.add_metadata(_merge_metadata(reader.metadata or {}, {META_KEY: json_meta}))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()

def sell(pdf_original: bytes,
         user_meta: Dict[str, Any],
         private_key,
         base_url: str = "https://mi-app.com/v/") -> Tuple[bytes, str]:
    doc_id = str(uuid.uuid4())
    verify_url = f"{base_url}{doc_id}"

    meta = {
        **user_meta,
        "id": doc_id,
        "uploaded_at": _utc_iso(),
        "verify_url": verify_url,
        "signature": SIGN_PLACEHOLDER
    }
    meta_json = json.dumps(meta, separators=(",", ":"))
    h = sha256(meta_json.encode()).digest()
    signature = firmar_hash(h, private_key)
    meta["signature"] = base64.b64encode(signature).decode()
    meta_json_signed = json.dumps(meta, separators=(",", ":"))

    pdf_meta = _embed_meta(pdf_original, meta_json_signed)

    qr_pdf_bytes = generar_pagina_qr_bytes(verify_url)
    qr_reader = PdfReader(BytesIO(qr_pdf_bytes))
    reader_final = PdfReader(BytesIO(pdf_meta))
    writer_final = PdfWriter()
    for p in reader_final.pages:
        writer_final.add_page(p)
    writer_final.add_page(qr_reader.pages[0])           # página del QR
    writer_final.add_metadata(reader_final.metadata)    # conserva metadatos

    out = BytesIO()
    writer_final.write(out)
    return out.getvalue(), doc_id

def verify(pdf_bytes: bytes, public_key) -> Tuple[bool, Dict[str, Any]]:
    reader = PdfReader(BytesIO(pdf_bytes))
    meta_raw = reader.metadata.get(META_KEY, "{}")
    meta = json.loads(str(meta_raw))

    sig_b64 = meta.get("signature", "")
    if sig_b64 in ("", SIGN_PLACEHOLDER):
        return False, meta

    signature = base64.b64decode(sig_b64)
    meta["signature"] = SIGN_PLACEHOLDER
    meta_json = json.dumps(meta, separators=(",", ":")).encode()
    h = sha256(meta_json).digest()
    valido = verificar_firma(h, signature, public_key)
    return valido, meta
