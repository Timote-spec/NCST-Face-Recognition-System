import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceService:
    def __init__(self):
        self.app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=-1)

    async def detect_faces(self, image_bytes: bytes) -> list[dict]:
        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes into a valid image")

        faces = self.app.get(img)

        results = []
        for f in faces:
            bbox = f.bbox.astype(int)  # [x1, y1, x2, y2]
            results.append({
                "embedding": f.embedding.tolist(),
                "bbox": {
                    "x": int(bbox[0]),
                    "y": int(bbox[1]),
                    "width": int(bbox[2] - bbox[0]),
                    "height": int(bbox[3] - bbox[1]),
                },
            })
        return results

    async def extract_embeddings(self, image_bytes: bytes) -> list[list[float]]:
        faces = await self.detect_faces(image_bytes)
        if len(faces) == 0:
            raise ValueError("No face detected in the image")
        return [f["embedding"] for f in faces]

    async def extract_embedding(self, image_bytes: bytes) -> list[float]:
        embeddings = await self.extract_embeddings(image_bytes)
        return embeddings[0]

    @staticmethod
    def embedding_to_blob(embedding: list[float]) -> bytes:
        return np.array(embedding, dtype=np.float32).tobytes()
