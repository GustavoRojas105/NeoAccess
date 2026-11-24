"""
NeoAccess - Descarga de modelos ONNX de OpenCV (YuNet + SFace)
Ubicación: raspberry_pi/descargar_modelos.py

Ejecutar UNA vez en la PC servidor y en cada Raspberry Pi:
    python descargar_modelos.py

Fuente oficial: repositorio OpenCV Model Zoo (https://github.com/opencv/opencv_zoo), licencia Apache-2.0 / MIT.
"""

import hashlib
import os
import sys
import urllib.request

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"


def _detector_for_installed_opencv():
    """YuNet 2023mar requiere OpenCV >= 4.8 (p. ej. python3-opencv de Raspberry Pi OS Bookworm es 4.6)."""
    try:
        import cv2
        major, minor = (int(x) for x in cv2.__version__.split(".")[:2])
        if (major, minor) < (4, 8):
            return "face_detection_yunet_2022mar.onnx"
    except Exception:
        pass
    return "face_detection_yunet_2023mar.onnx"


_DET = _detector_for_installed_opencv()

MODELS = [
    # (archivo, url, tamaño aproximado)
    (_DET, f"{ZOO}/face_detection_yunet/{_DET}", "~230 KB"),
    ("face_recognition_sface_2021dec.onnx",
     f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
     "~37 MB"),
]


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    for name, url, size in MODELS:
        dest = os.path.join(MODELS_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
            print(f"[OK] {name} ya existe.")
            continue
        print(f"[DESCARGA] {name} ({size}) desde {url}")
        tmp = dest + ".part"
        try:
            urllib.request.urlretrieve(url, tmp)
        except Exception as e:
            print(f"[ERROR] No se pudo descargar {name}: {e}")
            if os.path.exists(tmp):
                os.remove(tmp)
            sys.exit(1)
        with open(tmp, "rb") as f:
            head = f.read(200)
        if b"git-lfs" in head or head.lstrip().startswith(b"<"):
            os.remove(tmp)
            print(f"[ERROR] La descarga de {name} no es un modelo ONNX válido (posible puntero LFS o página HTML).")
            sys.exit(1)
        os.replace(tmp, dest)
        print(f"[OK] {name} guardado ({os.path.getsize(dest) // 1024} KB, sha256={sha256_of(dest)[:16]}...)")
    print("\nModelos listos en:", MODELS_DIR)


if __name__ == "__main__":
    main()
