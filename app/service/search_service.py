import os
from app.conn.es_conn import get_es_client
from app.analyze.analyzer import analyzer

class SearchService:
    def __init__(self):
        self.claims_index = os.getenv("ES_INDEX_CLAIMS", "claims_index")
        self.dtc_index = os.getenv("ES_INDEX_DTC", "dtc_index")

    async def search(self, query: str):
        # 1. Analyze Intent
        analysis_result = await analyzer.analyze(query)
        intent = analysis_result["intent"]
        params = analysis_result["parameters"]
        
        es = await get_es_client()
        
        # 2. Build Query based on Intent
        if analysis_result["route"] == "fast-path":
            dtc_code = params["dtc_code"]
            index = self.dtc_index
            
            # 우선 인덱스에서 검색 시도
            es_query = {"query": {"match": {"dtc_code": dtc_code}}}
            response = await es.search(index=index, body=es_query)
            
            # 만약 인덱스에 정보가 없다면? (조회할 때마다 쌓이는 로직)
            if response["hits"]["total"]["value"] == 0:
                # LLM에게 해당 DTC에 대한 설명 요청
                from app.llm.openai_service import openai_service
                dtc_info = await self._get_dtc_info_from_llm(dtc_code)
                
                # 인덱스에 저장 (다음에 조회할 때 사용)
                await es.index(index=index, document=dtc_info)
                
                # 검색 결과를 방금 생성한 정보로 대체
                result_hits = [dtc_info]
                total_count = 1
            else:
                result_hits = [hit["_source"] for hit in response["hits"]["hits"]]
                total_count = response["hits"]["total"]["value"]
        else:
            # Hybrid Search for other intents
            index = self.claims_index
            es_query = self._build_hybrid_query(analysis_result)
            response = await es.search(index=index, body=es_query)
            result_hits = [hit["_source"] for hit in response["hits"]["hits"]]
            total_count = response["hits"]["total"]["value"]
        
        # 4. Process Aggregations (Top Symptoms)
        top_symptoms = []
        if "aggregations" in response:
            buckets = response["aggregations"]["top_symptoms"]["buckets"]
            top_symptoms = [{"symptom": b["key"], "count": b["doc_count"]} for b in buckets]

        # 결과에서 벡터 데이터 제외 (가독성 및 응답 크기 최적화)
        for hit in result_hits:
            if isinstance(hit, dict):
                hit.pop("content_vector", None)
                hit.pop("symptom_vector", None)

        # 5. Generate Natural Language Answer
        from app.llm.openai_service import openai_service
        answer = await openai_service.generate_answer(query, result_hits)
        
        result = {
            "intent": intent,
            "route": analysis_result["route"],
            "parameters": params,
            "answer": answer, # 자연어 답변 추가
            "results": result_hits,
            "top_statistics": top_symptoms,
            "total": total_count,
            "source": analysis_result.get("source", "unknown")
        }

        # 5. Log the search activity (비동기 저장)
        try:
            from datetime import datetime
            log_index = os.getenv("ES_INDEX_LOGS", "jjc_search_logs_index")
            # ES 로그 저장 시에는 벡터 포함 가능 (선택 사항)
            await es.index(index=log_index, document={
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "intent": intent,
                "parameters": params,
                "total_results": result["total"]
            })
        except Exception as log_err:
            print(f"Logging failed: {log_err}")

        return result

    async def _get_dtc_info_from_llm(self, dtc_code: str):
        from app.llm.openai_service import openai_service
        return await openai_service.get_dtc_details(dtc_code)

    def _build_hybrid_query(self, analysis):
        params = analysis["parameters"]
        embedding = analysis.get("embedding")
        
        # None 값이 포함될 수 있으므로 필터링 후 join
        symptom_list = params.get("symptom") or []
        symptoms = " ".join([s for s in symptom_list if s is not None])
        
        # 쿼리 구성 (실제 인덱스 필드명 반영)
        main_query = {
            "bool": {
                "must": [
                    {"range": {"확정일자": {"gte": params.get("start_date") or "20200101", "lte": params.get("end_date") or "20261231"}}}
                ]
            }
        }

        # 키워드가 있으면 should 절 추가, 없으면 match_all
        if symptoms or params.get("model"):
            main_query["bool"]["should"] = [
                {"match": {"상세내용": symptoms}},
                {"match": {"차종": params.get("model") or ""}}
            ]
        else:
            main_query["bool"]["must"].append({"match_all": {}})

        # 기본 쿼리 구조
        sort_order = params.get("sort_order") or "desc"
        query = {
            "query": main_query,
            "aggs": {
                "top_symptoms": {
                    "terms": {
                        "field": "상세내용.keyword",
                        "size": 10,
                        "order": {"_count": sort_order}
                    }
                }
            },
            "size": 10
        }

        # Embedding이 있을 경우에만 knn 절 추가 (VALUE_NULL 오류 방지)
        if embedding and any(v != 0.0 for v in embedding):
            query["knn"] = {
                "field": "content_vector",
                "query_vector": embedding,
                "k": 10,
                "num_candidates": 100
            }
            
        return query

search_service = SearchService()
