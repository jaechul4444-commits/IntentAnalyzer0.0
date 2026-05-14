from app.conn.es_conn import es_client

async def get_nori_tokens(query: str):
    """
    Elasticsearch의 Nori 분석기를 사용하여 텍스트를 토큰화하고 상세 정보를 반환합니다.
    """
    try:
        # 기존에 생성된 인덱스의 nori_analyzer 사용
        response = await es_client.client.indices.analyze(
            index="jjc_claim_nori_v1",  # setup_es.py에서 설정한 인덱스 명
            body={
                "analyzer": "nori_analyzer",
                "text": query
            }
        )
        
        tokens = response["tokens"]
        
        # 상세 데이터 (JSONB 저장용)
        token_details = [
            {
                "token": t["token"],
                "pos": t["type"],
                "start_offset": t["start_offset"],
                "end_offset": t["end_offset"]
            } for t in tokens
        ]
        
        # 단순 토큰 리스트 (TEXT[] 저장용)
        token_list = [t["token"] for t in tokens]
        
        return token_details, token_list
    except Exception as e:
        print(f"Tokenization Error: {e}")
        return [], []
