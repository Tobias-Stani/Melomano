import io
import base64
from PIL import Image

MAX_PX   = 1200   # lado más largo
QUALITY  = 82     # JPEG quality (0-100)


def compress_image(raw: bytes) -> tuple[bytes, str]:
    """
    Recibe bytes de cualquier imagen, devuelve (bytes_comprimidos, mime_type).
    Redimensiona a MAX_PX en el lado más largo y convierte a JPEG.
    Si falla, devuelve los bytes originales sin tocar.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > MAX_PX:
            ratio = MAX_PX / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=QUALITY, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, "image/jpeg"


def compress_to_b64(raw: bytes) -> tuple[str, str]:
    """Devuelve (base64_string, mime_type)."""
    data, mime = compress_image(raw)
    return base64.b64encode(data).decode(), mime
