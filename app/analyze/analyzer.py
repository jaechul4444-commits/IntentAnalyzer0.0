import os
import sys
# 직접 실행 시 상위 패키지(app)를 찾을 수 있도록 sys.path 보정
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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
        
        # 3. Intent triggers for Template analysis
        self.intent_triggers = {
            "dtc_analysis": [r"고장코드", r"DTC", r"코드", r"경고등"],
            "trend_analysis": [r"가장\s*많이", r"가장\s*많은", r"몇\s*건", r"추이", r"통계", r"순위", r"빈번", r"가장\s*적은", r"발생\s*빈도", r"대비"],
            "cause_analysis": [r"원인", r"이유", r"왜", r"원인이", r"발생원인"],
            "similar_case": [r"사례", r"이력", r"조치", r"해결", r"수리", r"어떻게", r"방법"]
        }

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
            from dotenv import load_dotenv
            load_dotenv()
            es = await get_es_client()
            index_name = os.getenv("ES_INDEX_CLAIMS", "jjc_20260518_claim_test_index")

            
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

        # 0. RDB-Path: RDB 규칙 검증 (차대번호 정규식 패턴 및 RDB 고유 키워드 탐지 - 최우선 순위)
        import re
        vin_pattern = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b', re.IGNORECASE)
        has_vin = bool(vin_pattern.search(query))
        
        rdb_keywords = ["rdb", "db", "알디비", "디비", "실시간", "hqm", "csrs", "sql", "정형", "원장", "차대번호", "캠페인 번호", "로우 데이터", "정형데이터", "로우데이터", "국가"]
        is_rdb_by_keyword = any(k in query.lower() for k in rdb_keywords)
        
        if has_vin or is_rdb_by_keyword:
            extracted_keywords = {"model": None, "symptom": [], "part": []}
            for end_index, (category, word) in self.automaton.iter(query):
                if category == "model":
                    extracted_keywords["model"] = word
                else:
                    if word not in extracted_keywords[category]:
                        extracted_keywords[category].append(word)

            # 의도 트리거 매칭
            matched_intent = None
            for potential_intent, patterns in self.intent_triggers.items():
                for pattern in patterns:
                    if re.search(pattern, query):
                        matched_intent = potential_intent
                        break
                if matched_intent:
                    break

            # 날짜 파싱
            date_info = None
            date_pattern = re.compile(r"(\d+개월|\d+년\s*\d+월|\d+월|최근\s*\d+개월)")
            date_match = date_pattern.search(query)
            if date_match:
                date_info = date_match.group(1)
            
            start_date, end_date = parse_date_range(date_info)

            # 파라미터 구성
            parameters = {
                "symptom": list(set(extracted_keywords["symptom"] + extracted_keywords["part"])),
                "model": extracted_keywords["model"],
                "start_date": start_date,
                "end_date": end_date
            }

            # 만약 DTC 코드가 포함되어 있다면 파라미터에 추가
            dtc_match = self.dtc_pattern.search(query.upper())
            if dtc_match:
                parameters["dtc_code"] = dtc_match.group()
            print(f"\n[Branch 1 Hit]: RDB 규칙 적중 (차대번호/RDB 키워드) -> rdb-path 분기")

            # PostgreSQL Logging (RDB-path에서도 로그 저장 추가!)
            try:
                tokens, token_list = await get_nori_tokens(query)
                try:
                    embedding = await openai_service.get_embedding(query)
                except Exception as emb_err:
                    print(f"Embedding error in rdb-path: {emb_err}")
                    embedding = [0.0] * 1536
                await pg_client.save_query_log(
                    query_text=query,
                    tokens=tokens,
                    token_list=token_list,
                    intent=matched_intent or "similar_case",
                    parameters=parameters,
                    query_vector=embedding
                )
            except Exception as e:
                print(f"Logging Error in rdb-path: {e}")

            return {
                "route": "rdb-path",
                "intent": matched_intent or "similar_case",
                "parameters": parameters,
                "source": "rdb_direct"
            }


        # 0. PostgreSQL 기존 로그 확인 (캐시/참조)
        try:
            cached_result = await pg_client.find_similar_log(query)
            if cached_result:
                print(f"DEBUG: Found similar query in PG logs for: '{query}'")
                print(f"\n[Branch 2 Hit]: PostgreSQL 동일 캐시 적중 -> slow-path 분기 (토큰 0)")
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
            print(f"\n[Branch 3 Hit]: DTC 고장코드 패턴 탐지 -> fast-path 분기")

            # PostgreSQL Logging (Fast-path에서도 로그 저장 추가!)
            try:
                tokens, token_list = await get_nori_tokens(query)
                try:
                    embedding = await openai_service.get_embedding(query)
                except Exception as emb_err:
                    print(f"Embedding error in fast-path: {emb_err}")
                    embedding = [0.0] * 1536
                await pg_client.save_query_log(
                    query_text=query,
                    tokens=tokens,
                    token_list=token_list,
                    intent="dtc_analysis",
                    parameters={"dtc_code": dtc_code},
                    query_vector=embedding
                )
            except Exception as e:
                print(f"Logging Error in fast-path: {e}")

            return {
                "route": "fast-path",
                "intent": "dtc_analysis",
                "parameters": {"dtc_code": dtc_code}
            }

        # 2. Aho-Corasick Keyword Extraction (슬롯 필링)
        extracted_keywords = {"model": None, "symptom": [], "part": []}
        for end_index, (category, word) in self.automaton.iter(query):
            if category == "model":
                extracted_keywords["model"] = word
            else:
                if word not in extracted_keywords[category]:
                    extracted_keywords[category].append(word)

        # 3. Query Template 기반 초고속 1차 분류 및 의도 감지 시도 (LLM 호출 우회)
        matched_intent = None
        import re
        for potential_intent, patterns in self.intent_triggers.items():
            for pattern in patterns:
                if re.search(pattern, query):
                    matched_intent = potential_intent
                    break
            if matched_intent:
                break

        # 차종이나 증상/부품 키워드가 존재하고 의도 트리거가 감지된 경우 템플릿 처리 대상으로 판단
        is_template_target = False
        if (extracted_keywords["model"] or extracted_keywords["symptom"] or extracted_keywords["part"]) and matched_intent:
            is_template_target = True

        if is_template_target:
            print(f"DEBUG: Matching query '{query}' via Template Engine (Intent: {matched_intent})")
            
            # 정렬 순서 판별 (가장 많은=desc / 가장 적은=asc)
            sort_order = "desc"
            if re.search(r"가장\s*적은|최소|드문", query):
                sort_order = "asc"
                
            # 날짜 정보 Regex 추출
            date_info = None
            date_pattern = re.compile(r"(\d+개월|\d+년\s*\d+월|\d+월|최근\s*\d+개월)")
            date_match = date_pattern.search(query)
            if date_match:
                date_info = date_match.group(1)
                
            start_date, end_date = parse_date_range(date_info)
            
            # 파라미터 조합 (증상과 부품 키워드를 하나로 병합)
            parameters = {
                "symptom": list(set(extracted_keywords["symptom"] + extracted_keywords["part"])),
                "model": extracted_keywords["model"],
                "sort_order": sort_order,
                "start_date": start_date,
                "end_date": end_date
            }
            
            # 임베딩 생성 (오류 시 zero vector fallback)
            try:
                embedding = await openai_service.get_embedding(query)
            except Exception as emb_err:
                print(f"Embedding error in template engine: {emb_err}")
                embedding = [0.0] * 1536

            # PostgreSQL Logging
            try:
                tokens, token_list = await get_nori_tokens(query)
                await pg_client.save_query_log(
                    query_text=query,
                    tokens=tokens,
                    token_list=token_list,
                    intent=matched_intent,
                    parameters=parameters,
                    query_vector=embedding
                )
            except Exception as e:
                print(f"Logging Error in template engine: {e}")

            print(f"\n[Branch 4 Hit]: Aho-Corasick 템플릿 우회 엔진 적중 (LLM 우회) -> slow-path 분기")
            return {
                "route": "slow-path",
                "intent": matched_intent,
                "parameters": parameters,
                "embedding": embedding,
                "source": "template_engine"
            }

        # 4. Slow-Path: LLM extraction (Refinement & Intent) - 템플릿 미매칭 시 최종 수단
        try:
            llm_data = await openai_service.extract_parameters(query)
            intent = llm_data.get("intent", "similar_case")
            search_type = llm_data.get("search_type", "semantic")
            
            # LLM 결과와 Aho-Corasick 결과를 병합 (증상 및 부품 키워드 포함)
            parameters = {
                "symptom": list(set((llm_data.get("symptom") or []) + extracted_keywords["symptom"] + extracted_keywords["part"])),
                "model": llm_data.get("model") or extracted_keywords["model"],
                "sort_order": llm_data.get("sort_order", "desc"),
                "start_date": None,
                "end_date": None
            }
            # 날짜 파싱
            start_date, end_date = parse_date_range(llm_data.get("date_info"))
            parameters["start_date"] = start_date
            parameters["end_date"] = end_date
            
            # Embedding 생성
            embedding = await openai_service.get_embedding(query)
            
            # 만약 LLM이 정형 데이터를 직접 조회하는 structured 요청으로 판단한 경우 rdb-path로 우회
            if search_type == "structured":
                # DTC 코드가 포함되어 있다면 파라미터에 함께 실어줍니다.
                dtc_match = self.dtc_pattern.search(query.upper())
                if dtc_match:
                    parameters["dtc_code"] = dtc_match.group()
                    
                # PostgreSQL Logging
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
                except Exception as log_e:
                    print(f"Logging Error in LLM structured route: {log_e}")
                    
                print(f"\n[Branch 5-A Hit]: OpenAI LLM 시맨틱 라우터 판별 (search_type: structured) -> rdb-path 분기")
                return {
                    "route": "rdb-path",
                    "intent": intent,
                    "parameters": parameters,
                    "source": "llm_structured"
                }
            
        except Exception as e:
            # OpenAI Quota 초과 시 Fallback (Aho-Corasick 기반)
            print(f"OpenAI API Error (Fallback to Aho-Corasick): {e}")
            intent = "similar_case"
            parameters = {
                "symptom": list(set(extracted_keywords["symptom"] + extracted_keywords["part"])),
                "model": extracted_keywords["model"],
                "sort_order": "desc",
                "start_date": "20240101",
                "end_date": "20261231"
            }
            embedding = [0.0] * 1536

        # 5. PostgreSQL Logging
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
