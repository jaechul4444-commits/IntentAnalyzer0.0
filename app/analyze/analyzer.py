import os
import ahocorasick
from app.llm.openai_service import openai_service
from app.utils.date_parser import parse_date_range
from app.utils.token_service import get_nori_tokens
from app.conn.pg_conn import pg_client
from app.conn.es_conn import get_es_client

class IntentAnalyzer:
    def __init__(self):
        # 1. DTC pattern: 1 letter followed by 4 digits (e.g., P2261)
        import re
        self.dtc_pattern = re.compile(r'[PBUC]\d{4}')
        
        # 2. Setup Aho-Corasick Automaton for Keywords
        self.automaton = ahocorasick.Automaton()
        self.initialized = False
        self._setup_keywords() # Load defaults first

    def _setup_keywords(self):
        # 기본 하드코딩 키워드 (ES 로드 실패 시 또는 초기값으로 사용)
        keywords = {
            "model": ["그랜저", "아반떼", "쏘나타", "제네시스", "싼타페", "투싼", "팰리세이드", "Grandeur", "Avante", "Sonata"],
            "symptom": ["시동", "진동", "소음", "오일", "누유", "경고등", "출력", "변속", "브레이크", "에어컨"],
            "part": ["엔진", "미션", "배터리", "펌프", "어셈블리", "센서", "벨트", "필터", "타이어"]
        }
        for category, words in keywords.items():
            for word in words:
                if word not in self.automaton:
                    self.automaton.add_word(word, (category, word))
        self.automaton.make_automaton()

    async def update_keywords(self):
        """ES에서 실제 데이터 기반으로 키워드 자동 업데이트"""
        try:
            es = await get_es_client()
            index_name = os.getenv("ES_INDEX_CLAIMS", "jjc_claim_nori_v1")
            
            # 집계 쿼리 (차종, 부품명, 현상)
            agg_query = {
                "size": 0,
                "aggs": {
                    "models": {"terms": {"field": "차종.keyword", "size": 100}},
                    "parts": {"terms": {"field": "부품명.keyword", "size": 100}},
                    "symptoms": {"terms": {"field": "현상.keyword", "size": 100}}
                }
            }
            
            response = await es.search(index=index_name, body=agg_query)
            aggs = response.get("aggregations", {})
            
            new_keywords = {
                "model": [b["key"] for b in aggs.get("models", {}).get("buckets", [])],
                "part": [b["key"] for b in aggs.get("parts", {}).get("buckets", [])],
                "symptom": [b["key"] for b in aggs.get("symptoms", {}).get("buckets", [])]
            }
            
            # 오토마타 재구축 (기본값 + 동적 키워드)
            self.automaton = ahocorasick.Automaton()
            self._setup_keywords() # 기본값 로드
            
            # ES에서 가져온 실데이터 키워드 추가
            for category, words in new_keywords.items():
                for word in words:
                    if word and word not in self.automaton:
                        self.automaton.add_word(word, (category, word))
            
            self.automaton.make_automaton()
            self.initialized = True
            print(f"DEBUG: Keywords updated from ES index '{index_name}'")
            
        except Exception as e:
            print(f"WARNING: Could not update keywords from ES (using defaults): {e}")
            # 에러가 나도 기본값은 이미 로드되어 있으므로 initialized 처리는 하지 않음 (나중에 재시도 가능)

    async def analyze(self, query: str):
        # 0. 키워드 초기화 확인 (최초 1회 동적 로드)
        if not self.initialized:
            await self.update_keywords()

        # 0. PostgreSQL 기존 로그 확인 (캐시/참조)
        try:
            cached_result = await pg_client.find_similar_log(query)
            if cached_result:
                print(f"DEBUG: Found similar query in PG logs for: '{query}'")
                return {
                    "route": "slow-path",
                    "intent": cached_result["intent"],
                    "parameters": cached_result["parameters"],
                    "embedding": cached_result["embedding"],
                    "source": "pg_cache"
                }
        except Exception as e:
            print(f"PG Search Error: {e}")

        # 1. Fast-Path: Check for DTC codes
        dtc_match = self.dtc_pattern.search(query.upper())
        if dtc_match:
            dtc_code = dtc_match.group()
            return {
                "route": "fast-path",
                "intent": "dtc_analysis",
                "parameters": {"dtc_code": dtc_code}
            }

        # 2. Aho-Corasick Keyword Extraction
        extracted_keywords = {"model": None, "symptom": [], "part": []}
        for end_index, (category, word) in self.automaton.iter(query):
            if category == "model":
                extracted_keywords["model"] = word
            else:
                if word not in extracted_keywords[category]:
                    extracted_keywords[category].append(word)

        # 3. Slow-Path: LLM extraction (Refinement & Intent)
        try:
            llm_data = await openai_service.extract_parameters(query)
            intent = llm_data.get("intent", "similar_case")
            # LLM 결과와 Aho-Corasick 결과를 병합
            parameters = {
                "symptom": list(set((llm_data.get("symptom") or []) + extracted_keywords["symptom"])),
                "model": llm_data.get("model") or extracted_keywords["model"],
                "sort_order": llm_data.get("sort_order", "desc"), # 정렬 순서 추가
                "start_date": None,
                "end_date": None
            }
            # 날짜 파싱
            start_date, end_date = parse_date_range(llm_data.get("date_info"))
            parameters["start_date"] = start_date
            parameters["end_date"] = end_date
            
            # Embedding 생성
            embedding = await openai_service.get_embedding(query)
            
        except Exception as e:
            # OpenAI Quota 초과 시 Fallback (Aho-Corasick 기반)
            print(f"OpenAI API Error (Fallback to Aho-Corasick): {e}")
            intent = "similar_case"
            parameters = {
                "symptom": extracted_keywords["symptom"],
                "model": extracted_keywords["model"],
                "sort_order": "desc",
                "start_date": "20240101", # 임시 기본값
                "end_date": "20261231"
            }
            embedding = [0.0] * 1536

        # 4. PostgreSQL Logging
        try:
            tokens, token_list = await get_nori_tokens(query)
            await pg_client.save_query_log(
                query_text=query,
                tokens=tokens,
                token_list=token_list,
                intent=intent,
                parameters=parameters,
                query_vector=embedding
            )
        except Exception as e:
            print(f"Logging Error: {e}")

        return {
            "route": "slow-path",
            "intent": intent,
            "parameters": parameters,
            "embedding": embedding,
            "source": "llm_analysis"
        }

analyzer = IntentAnalyzer()
