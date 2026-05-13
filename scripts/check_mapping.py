import asyncio
import os
import json
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.conn.es_conn import get_es_client
from dotenv import load_dotenv

load_dotenv()

async def check_index():
    es = await get_es_client()
    index_name = os.getenv("ES_INDEX_CLAIMS")
    
    print(f"--- Checking Index: {index_name} ---")
    
    try:
        # 1. 매핑 확인
        mapping = await es.indices.get_mapping(index=index_name)
        print("\n[1] Index Mapping:")
        print(json.dumps(mapping[index_name]["mappings"], indent=2, ensure_ascii=False))
        
        # 2. 데이터 샘플 1건 확인
        sample = await es.search(index=index_name, size=1)
        print("\n[2] Sample Document:")
        if sample["hits"]["hits"]:
            print(json.dumps(sample["hits"]["hits"][0]["_source"], indent=2, ensure_ascii=False))
        else:
            print("No documents found in this index.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await es.close()

if __name__ == "__main__":
    asyncio.run(check_index())
