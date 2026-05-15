import re
import ahocorasick
from app.llm.openai_service import openai_service
from app.utils.date_parser import parse_date_range
from app.utils.token_service import get_nori_tokens
from app.conn.pg_conn import pg_client

class IntentAnalyzer:
    def __init__(self):
        # 1. DTC pattern: 1 letter followed by 4 digits (e.g., P2261)
        self.dtc_pattern = re.compile(r'[PBUC]\d{4}')
        
        # 2. Setup Aho-Corasick Automaton for Keywords
        self.automaton = ahocorasick.Automaton()
        self._setup_keywords()

    def _setup_keywords(self):
        # 인덱스 매핑 기반 주요 키워드 (실제 운영 시에는 DB/ES에서 동적으로 로드 가능)
        keywords = {
            "model": ["그랜저", "아반떼", "쏘나타", "제네시스", "싼타페", "투싼", "팰리세이드", "Grandeur", "Avante", "Sonata"],
            "symptom": ["시동", "진동", "소음", "오일", "누유", "경고등", "출력", "변속", "브레이크", "에어컨"],
            "part": ["엔진", "미션", "배터리", "펌프", "어셈블리", "센서", "벨트", "필터", "타이어"]
        }
        for category, words in keywords.items():
            for word in words:
                self.automaton.add_word(word, (category, word))
        self.automaton.make_automaton()

    async def analyze(self, query: str):
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
