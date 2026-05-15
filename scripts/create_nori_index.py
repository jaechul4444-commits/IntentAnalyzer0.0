import asyncio
import os
import json
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

load_dotenv()

async def create_nori_index():
    es = AsyncElasticsearch(
        os.getenv("ES_HOST", "http://localhost:9200"),
        basic_auth=(os.getenv("ES_USER"), os.getenv("ES_PASSWORD")) if os.getenv("ES_USER") else None,
        verify_certs=False
    )

    # 1. Load existing index info
    info_path = "scripts/index_info.json"
    if not os.path.exists(info_path):
        print(f"Error: {info_path} not found. Please run get_index_details.py first.")
        return

    with open(info_path, "r", encoding="utf-8") as f:
        info = json.load(f)

    existing_mapping = info.get("mapping", {}).get("properties", {})
    sample_data = info.get("sample", {})

    # 2. Define Nori settings
    nori_settings = {
        "analysis": {
            "analyzer": {
                "nori_analyzer": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "decompound_mode": "mixed",
                    "filter": ["nori_readingform", "lowercase"]
                }
            },
            "tokenizer": {
                "nori_tokenizer": {
                    "type": "nori_tokenizer",
                    "decompound_mode": "mixed"
                }
            }
        }
    }

    # 3. Transform mapping
    new_properties = {}
    
    # Date fields identification (heuristic)
    date_fields = ["확정일자", "판매일자", "등록일", "완료일", "수정일", "요청일자", "생산일자", "회수일", "입력일", "분석일", "긴급마감일"]

    for field_name, field_config in existing_mapping.items():
        new_config = field_config.copy()
        
        # If it's a text field, add nori analyzer
        if new_config.get("type") == "text":
            new_config["analyzer"] = "nori_analyzer"
            # Ensure keyword sub-field exists for sorting/aggregation if it was there
            if "fields" not in new_config:
                new_config["fields"] = {"keyword": {"type": "keyword", "ignore_above": 256}}
        
        # Special handling for date fields that might be mapped as text
        if field_name in date_fields and new_config.get("type") == "text":
            sample_val = sample_data.get(field_name)
            if sample_val and isinstance(sample_val, str) and len(sample_val) == 8 and sample_val.isdigit():
                print(f"Converting {field_name} to date type based on sample data: {sample_val}")
                new_config = {
                    "type": "date",
                    "format": "yyyyMMdd||epoch_millis"
                }

        new_properties[field_name] = new_config

    # 4. Create the new index
    new_index_name = "jjc_claim_nori_v1"
    
    body = {
        "settings": nori_settings,
        "mappings": {
            "properties": new_properties
        }
    }

    if await es.indices.exists(index=new_index_name):
        print(f"Index {new_index_name} already exists. Deleting...")
        await es.indices.delete(index=new_index_name)

    await es.indices.create(index=new_index_name, body=body)
    print(f"Successfully created index: {new_index_name}")

    await es.close()

if __name__ == "__main__":
    asyncio.run(create_nori_index())
