 
import json
import uuid

from qdrant_client.models import PointStruct
from app.rag.qdrant_client import client
from app.rag.embeddings import embed_text  # wrapper on bge-m3

def ingest_compliance_docs(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    points = []
    for entry in entries:
         # todo el schema completo como metadata
        embed_source = f"{entry['category']}: {entry['defect_description']}"
        vector = embed_text(embed_source)

        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=entry,  # todo el schema completo como metadata
        ))

    client.upsert(collection_name="mtn_rtm_docs", points=points)
    print(f"Ingested {len(points)} compliance entries.")