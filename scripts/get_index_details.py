import asyncio
import os
import json
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.conn.es_conn import get_es_client
from dotenv import load_dotenv

load_dotenv()

async def get_details():
    es = await get_es_client()
    index_name = os.getenv("ES_INDEX_CLAIMS")
    
    try:
        mapping = await es.indices.get_mapping(index=index_name)
        sample = await es.search(index=index_name, size=1)
        
        info = {
            "mapping": mapping[index_name]["mappings"],
            "sample": sample["hits"]["hits"][0]["_source"] if sample["hits"]["hits"] else {}
        }
        
        # 파일로 저장 (UTF-8)
        with open("scripts/index_info.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
            
        print("Success: Index information saved to scripts/index_info.json")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await es.close()

if __name__ == "__main__":
    asyncio.run(get_details())
