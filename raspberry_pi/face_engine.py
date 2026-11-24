"""
NeoAccess - Motor de Reconocimiento Facial compartido (Servidor + Raspberry Pi)
Ubicación: raspberry_pi/face_engine.py

Usa los modelos ONNX de OpenCV:
  - YuNet  -> detección de rostro y 5 puntos faciales
  - SFace  -> vector (embedding) de 128 dimensiones

El MISMO motor genera los vectores al registrar (servidor / Dashboard) y al
reconocer (puerta), por lo que los vectores son comparables entre sí.
La comparación es por similitud coseno (1.0 = idéntico).

CUMPLIMIENTO RF-07: las imágenes solo viven en RAM durante la extracción;
nunca se escriben a disco. Quien llama debe descartar el frame tras usarlo.

Modelos: ejecutar `python descargar_modelos.py` (se guardan en raspberry_pi/models/).
"""

import glob
import math
import os

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# Umbral recomendado por OpenCV para SFace con similitud coseno
DEFAULT_COSINE_THRESHOLD = 0.363
# Confianza mínima de detección de YuNet
DEFAULT_DETECTION_SCORE = 0.85
# Tamaño mínimo del rostro (px) para considerarlo "frente a la puerta"
DEFAULT_MIN_FACE_PX = 60

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False


class FaceEngineUnavailable(RuntimeError):
    """OpenCV o los modelos ONNX no están disponibles."""


def _find_model(pattern: str):
    matches = sorted(glob.glob(os.path.join(MODELS_DIR, pattern)), reverse=True)
    return matches[0] if matches else None


def _opencv_version_tuple():
    try:
        return tuple(int(x) for x in cv2.__version__.split(".")[:2])
    except Exception:
        return (0, 0)


def _pick_detector_model():
    """YuNet 2023mar requiere OpenCV >= 4.8; con versiones anteriores se usa 2022mar."""
    if OPENCV_AVAILABLE and _opencv_version_tuple() < (4, 8):
        return _find_model("face_detection_yunet_2022mar*.onnx")
    return _find_model("face_detection_yunet_2023mar*.onnx") or _find_model("face_detection_yunet*.onnx")


def engine_status() -> dict:
    """Diagnóstico legible del motor (útil para test_conexion y el Dashboard)."""
    return {
        "opencv": OPENCV_AVAILABLE,
        "opencv_version": cv2.__version__ if OPENCV_AVAILABLE else None,
        "modelo_deteccion": _pick_detector_model(),
        "modelo_reconocimiento": _find_model("face_recognition_sface*.onnx"),
    }


class FaceEngine:
    def __init__(self, score_threshold: float = DEFAULT_DETECTION_SCORE, min_face_px: int = DEFAULT_MIN_FACE_PX):
        if not OPENCV_AVAILABLE:
            raise FaceEngineUnavailable(
                "OpenCV no está instalado. Instale 'opencv-python-headless' (PC) o 'python3-opencv' (Raspberry Pi)."
            )
        det_path = _pick_detector_model()
        rec_path = _find_model("face_recognition_sface*.onnx")
        if not det_path or not rec_path:
            raise FaceEngineUnavailable(
                f"Faltan los modelos ONNX en {MODELS_DIR}. Ejecute: python descargar_modelos.py"
            )
        self.min_face_px = min_face_px
        self.detector = cv2.FaceDetectorYN.create(det_path, "", (320, 320), score_threshold, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(rec_path, "")

    def detect_largest_face(self, frame_bgr):
        """Devuelve la fila de detección del rostro más grande o None."""
        h, w = frame_bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame_bgr)
        if faces is None or len(faces) == 0:
            return None
        face = max(faces, key=lambda f: f[2] * f[3])
        if min(face[2], face[3]) < self.min_face_px:
            return None
        return face

    def extract_vector(self, frame_bgr):
        """
        Extrae el vector de 128-d del rostro más grande del frame.
        Retorna (vector: list[float], score_deteccion: float) o (None, 0.0) si no hay rostro.
        """
        face = self.detect_largest_face(frame_bgr)
        if face is None:
            return None, 0.0
        aligned = self.recognizer.alignCrop(frame_bgr, face)
        feature = self.recognizer.feature(aligned)
        del aligned  # RF-07
        return feature.flatten().astype(float).tolist(), float(face[-1])

    def extract_vector_from_bytes(self, image_bytes: bytes):
        """Decodifica una imagen (JPEG/PNG) en RAM y extrae su vector. La imagen no se guarda."""
        buf = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("La imagen no se pudo decodificar.")
        try:
            return self.extract_vector(frame)
        finally:
            del frame  # RF-07


# -------------------------------------------------------------
# Comparación (sin dependencias: funciona aunque no haya numpy)
# -------------------------------------------------------------
def cosine_similarity(v1, v2) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return -1.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return -1.0
    return dot / (n1 * n2)


class VectorIndex:
    """
    Índice en memoria de vectores registrados para buscar el más parecido rápido.
    Con numpy normaliza una sola vez y compara todos los usuarios en una operación.
    """

    def __init__(self, usuarios: list):
        self.usuarios = [u for u in usuarios if u.get("vector_encoding")]
        self._matrix = None
        if np is not None and self.usuarios:
            m = np.array([u["vector_encoding"] for u in self.usuarios], dtype=np.float32)
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._matrix = m / norms

    def best_match(self, vector):
        """Retorna (usuario | None, similitud_maxima)."""
        if not self.usuarios or not vector:
            return None, -1.0
        if self._matrix is not None:
            v = np.asarray(vector, dtype=np.float32)
            n = np.linalg.norm(v)
            if n == 0 or v.shape[0] != self._matrix.shape[1]:
                return None, -1.0
            sims = self._matrix @ (v / n)
            idx = int(np.argmax(sims))
            return self.usuarios[idx], float(sims[idx])
        best, best_sim = None, -1.0
        for u in self.usuarios:
            s = cosine_similarity(vector, u["vector_encoding"])
            if s > best_sim:
                best, best_sim = u, s
        return best, best_sim
