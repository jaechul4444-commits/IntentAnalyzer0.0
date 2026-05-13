import asyncio
import os
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

load_dotenv()

async def setup_indices():
    es = AsyncElasticsearch(
        os.getenv("ES_HOST", "http://localhost:9200"),
        basic_auth=(os.getenv("ES_USER"), os.getenv("ES_PASSWORD")) if os.getenv("ES_USER") else None,
        verify_certs=False
    )

    claims_index = os.getenv("ES_INDEX_CLAIMS", "claims_index")
    dtc_index = os.getenv("ES_INDEX_DTC", "dtc_index")

    # 1. Claims Index with Nori and Vector Field
    claims_settings = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "nori_analyzer": {
                        "type": "custom",
                        "tokenizer": "nori_tokenizer",
                        "decompound_mode": "mixed"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "symptom_description": {
                    "type": "text", 
                    "analyzer": "nori_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword"}
                    }
                },
                "model_name": {"type": "keyword"},
                "occurrence_date": {"type": "date", "format": "yyyyMMdd"},
                "symptom_vector": {
                    "type": "dense_vector",
                    "dims": 1536, # text-embedding-3-small dimension
                    "index": True,
                    "similarity": "cosine"
                }
            }
        }
    }

    # 2. DTC Index
    dtc_settings = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "nori_analyzer": {
                        "type": "custom",
                        "tokenizer": "nori_tokenizer",
                        "decompound_mode": "mixed"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "dtc_code": {"type": "keyword"},
                "description": {"type": "text", "analyzer": "nori_analyzer"},
                "cause": {"type": "text", "analyzer": "nori_analyzer"}
            }
        }
    }

    # if await es.indices.exists(index=claims_index):
    #     await es.indices.delete(index=claims_index)
    # await es.indices.create(index=claims_index, body=claims_settings)

    if await es.indices.exists(index=dtc_index):
        await es.indices.delete(index=dtc_index)
    await es.indices.create(index=dtc_index, body=dtc_settings)

    print("Indices created successfully.")
    await es.close()

if __name__ == "__main__":
    asyncio.run(setup_indices())
