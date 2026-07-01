import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceService:
    def __init__(self):
        self.app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=-1)

    async def extract_embedding(self, image_bytes: bytes) -> list[float]:
        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes into a valid image")

        faces = self.app.get(img)

        if len(faces) == 0:
            raise ValueError("No face detected in the image")
        if len(faces) > 1:
            raise ValueError(f"Multiple faces detected ({len(faces)}); expected exactly one")

        return faces[0].embedding.tolist()

    @staticmethod
    def embedding_to_blob(embedding: list[float]) -> bytes:
        return np.array(embedding, dtype=np.float32).tobytes()
