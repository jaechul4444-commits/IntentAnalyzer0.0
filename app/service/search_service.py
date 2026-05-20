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
        
        # 2. Build Query based on Intent using ES Search Templates and RDB route
        if analysis_result["route"] == "rdb-path":
            # PostgreSQL RDB Direct Query Execution
            from app.conn.pg_conn import pg_client
            
            base_sql = """
SELECT
            A.COMPANYCODE, A.SER_NO, A.TYPE, A.CAR_TYPE, A.PRJ_NM,
            A.ITMNO, A.REP_ITMNO, A.ITMNM, A.SYST, A.SYM_CD,
            A.SYM_NM, A.CAUSE, A.CAUSE_NM, A.SIG_CONT, A.DTC1,
            A.DTC2, A.DTC3, A.WARN_YN, A.PRO_YMD, A.PRO_YM,
            A.SAL_YMD, A.SAL_YM, A.RPR_YMD, A.RPR_YM, A.CONF_YMD,
            A.CONF_YM, A.JQTY_DAY, A.USE_DAY, A.MILEAGE, A.CNT,
            A.PAY_ITM, A.PAY_GOG, A.PAY_OUT, A.PAY_TOT, A.COMB_RONO,
            A.RONO, A.NATION_NM, A.AREA_NM, A.RO_AREA_CD, A.RO_AREA_NM,
            A.RO_AREA, A.CUST_CD, A.CUST_NM, A.PAY_CUST_CD, A.PAY_CUST_NM,
            A.GSW_ATTR_CUST, A.WRK_CD, A.SAL_GUBN, A.VIN, A.MI_CODE,
            A.OPT_CODE, A.VERSION, A.RAW_ENG_CD, A.TRANS_NO, A.PROD_COMPANYCODE,
            A.FACT_NM, A.RAW_ENG_NM, A.RAW_ENGINE_PROD_DT, A.TRANS_PRJ_CD, A.NON_QLTY_CLAIM_YN,
            A.DTC4, A.DTC5, A.VAATZ_EVAL_CUST_CD, A.VAATZ_EVAL_CUST_NM, A.MOB_PAY,
            A.GLV_PAY, A.CAMP_NO, A.CAMP_NM, A.REGCO, A.REGID,
            A.REGDAT, A.UPDID, A.UPDDAT,
            

            -- Original Codes
            A.MAP_ITMNM,
            A.MAP_CAR_PUM,
            A.MAP_CLMGB,
            A.MAP_MILEAGE,
            A.MAP_CAR_TYPE,
            A.MAP_TOTENG,
            A.MAP_DESC,
            A.MAP_IMPU,
            
            -- Decoded Korean Names
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0029', A.MAP_ITMNM) AS MAP_ITMNM_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0028', A.MAP_CAR_PUM) AS MAP_CAR_PUM_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0031', A.MAP_CLMGB) AS MAP_CLMGB_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0032', A.MAP_MILEAGE) AS MAP_MILEAGE_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0027', A.MAP_CAR_TYPE) AS MAP_CAR_TYPE_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0033', A.MAP_TOTENG) AS MAP_TOTENG_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0016', A.MAP_DESC) AS MAP_DESC_NAME,
            PCMLIB.UF_GET_HQMCODENAME(A.COMPANYCODE, 'KO', 'CMN', 'CMN0017', A.MAP_IMPU) AS MAP_IMPU_NAME,
            -- B columns (excluding duplicate metadata and join keys)
            B.TYPE_CD, B.CHG_CD, B.REACT_CD, B.CHG2_CD, B.SVY_TX, B.CLT_YN, 
            B.CLT_YMD, B.SCPL_YN, B.SCPL_YMD, B.GRADE_CD, B.MTN_MAN, B.MTN_CALL, 
            B.ETC_TX AS SVY_ETC_TX, B.QIR_YN, B.UPDCO AS SVY_UPDCO,
            
            -- C columns (excluding duplicate metadata and join keys)
            C.CLTD_YMD, C.REP_YMD, C.ADD_YMD, C.RES_SB,
            C.CLM_FL1, C.CLM_FL2, C.CLM_FL3, C.CLM_FL4, C.CLM_FL5, C.SUM_FL, 
            C.DTL_TX, C.CAU_TX, C.CTR_TX, C.REP_ST, C.OLD_CAR, C.CLM_FL6, 
            C.CLM_FL7, C.CLM_FL8, C.CLM_FL9, C.VEND
        FROM
            PQMLIB.HQM_TOT_CSRS1000 A
                LEFT OUTER JOIN PQMLIB.HQM_SVY B
                    ON A.COMPANYCODE = B.COMPANYCODE
                    AND A.CONF_YMD = B.CFM_YMD
                    AND A.SER_NO = B.SER_NO
                LEFT OUTER JOIN PQMLIB.HQM_REP C
                    ON A.COMPANYCODE = C.COMPANYCODE
                    AND A.CONF_YMD = C.CFM_YMD
                    AND A.SER_NO = C.SER_NO
"""
            where_clauses = []
            sql_params = []
            param_counter = 1
            
            # 1. 차종 필터링 (model)
            if params.get("model"):
                model_val = f"%{params['model']}%"
                where_clauses.append(f"(A.CAR_TYPE LIKE ${param_counter} OR A.PRJ_NM LIKE ${param_counter})")
                sql_params.append(model_val)
                param_counter += 1
                
            # 2. 증상 및 부품 키워드 필터링 (symptom)
            symptom_list = params.get("symptom") or []
            if symptom_list:
                symptom_conds = []
                for sym in symptom_list:
                    if sym:
                        symptom_conds.append(f"(A.SYM_NM LIKE ${param_counter} OR A.CAUSE_NM LIKE ${param_counter} OR A.SIG_CONT LIKE ${param_counter} OR A.ITMNM LIKE ${param_counter})")
                        sql_params.append(f"%{sym}%")
                        param_counter += 1
                if symptom_conds:
                    where_clauses.append(f"({' OR '.join(symptom_conds)})")
                    
            # 3. 날짜 필터링
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            if start_date:
                where_clauses.append(f"A.CONF_YMD >= ${param_counter}")
                sql_params.append(start_date)
                param_counter += 1
            if end_date:
                where_clauses.append(f"A.CONF_YMD <= ${param_counter}")
                sql_params.append(end_date)
                param_counter += 1
                
            # 4. DTC 고장코드 필터링
            if params.get("dtc_code"):
                where_clauses.append(f"(A.DTC1 = ${param_counter} OR A.DTC2 = ${param_counter} OR A.DTC3 = ${param_counter} OR A.DTC4 = ${param_counter} OR A.DTC5 = ${param_counter})")
                sql_params.append(params["dtc_code"])
                param_counter += 1

            sql = base_sql
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
                
            # 최신순 정렬 및 개수 제한
            sql += " ORDER BY A.CONF_YMD DESC LIMIT 50"
            
            try:
                # 1. 시도: 사용자가 제공한 원본 대형 조인 쿼리 실행
                result_hits = await pg_client.execute_select_query(sql, sql_params)
                total_count = len(result_hits)
            except Exception as e:
                # 2. 폴백: 테이블/스키마 부재 시 실제 존재하는 public.hqm_csrs1000 단일 테이블 조회
                print(f"Original RDB query failed (falling back to public.hqm_csrs1000): {e}")
                
                fallback_where = []
                fallback_params = []
                f_counter = 1
                
                if params.get("model"):
                    fallback_where.append(f"(chj_nm LIKE ${f_counter} OR car_type LIKE ${f_counter})")
                    fallback_params.append(f"%{params['model']}%")
                    f_counter += 1
                    
                symptom_list = params.get("symptom") or []
                if symptom_list:
                    sym_conds = []
                    for sym in symptom_list:
                        if sym:
                            sym_conds.append(f"(ro_tx LIKE ${f_counter} OR itm_nm LIKE ${f_counter} OR req_tx LIKE ${f_counter})")
                            fallback_params.append(f"%{sym}%")
                            f_counter += 1
                    if sym_conds:
                        fallback_where.append(f"({' OR '.join(sym_conds)})")
                        
                start_date = params.get("start_date")
                end_date = params.get("end_date")
                if start_date:
                    fallback_where.append(f"cfm_ymd >= ${f_counter}")
                    fallback_params.append(start_date)
                    f_counter += 1
                if end_date:
                    fallback_where.append(f"cfm_ymd <= ${f_counter}")
                    fallback_params.append(end_date)
                    f_counter += 1
                    
                if params.get("dtc_code"):
                    fallback_where.append(f"dtc_cd = ${f_counter}")
                    fallback_params.append(params["dtc_code"])
                    f_counter += 1
                    
                fallback_sql = """
SELECT 
    companycode AS "COMPANYCODE",
    ser_no AS "SER_NO",
    car_type AS "CAR_TYPE",
    chj_nm AS "PRJ_NM",
    itmno AS "ITMNO",
    itm_nm AS "ITMNM",
    sym_cd AS "SYM_CD",
    ro_tx AS "SIG_CONT",
    dtc_cd AS "DTC1",
    pro_ymd AS "PRO_YMD",
    sal_ymd AS "SAL_YMD",
    rep_ymd AS "RPR_YMD",
    mileage AS "MILEAGE",
    rono AS "RONO",
    vinno AS "VIN",
    regdat AS "REGDAT"
FROM
    public.hqm_csrs1000
"""
                if fallback_where:
                    fallback_sql += " WHERE " + " AND ".join(fallback_where)
                fallback_sql += " ORDER BY cfm_ymd DESC LIMIT 50"
                
                try:
                    result_hits = await pg_client.execute_select_query(fallback_sql, fallback_params)
                    total_count = len(result_hits)
                except Exception as fb_e:
                    print(f"Fallback RDB query also failed: {fb_e}")
                    result_hits = [{"error": f"RDB Query execution failed: {str(fb_e)}"}]
                    total_count = 0


        elif analysis_result["route"] == "fast-path":
            dtc_code = params["dtc_code"]
            index = self.dtc_index
            template_id = "dtc_analysis_template"
            
            # 우선 인덱스에서 템플릿 검색 시도
            try:
                response = await es.search_template(
                    index=index,
                    body={
                        "id": template_id,
                        "params": {"dtc_code": dtc_code}
                    }
                )
            except Exception as e:
                print(f"DTC Template search failed, falling back to direct match query: {e}")
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
            # Hybrid Search for other intents using Mustache Search Templates
            index = self.claims_index
            template_id = f"{intent}_template"
            
            # 파라미터 빌딩
            symptom_list = params.get("symptom") or []
            symptoms = " ".join([s for s in symptom_list if s is not None])
            
            es_params = {
                "start_date": params.get("start_date") or "20200101",
                "end_date": params.get("end_date") or "20261231"
            }
            if symptoms:
                es_params["symptom"] = symptoms
            if params.get("model"):
                es_params["model"] = params["model"]
            if params.get("sort_order"):
                es_params["sort_order"] = params["sort_order"]
                
            # Embedding이 있을 경우 query_vector 추가
            embedding = analysis_result.get("embedding")
            if embedding and any(v != 0.0 for v in embedding):
                es_params["query_vector"] = embedding
                
            print(f"DEBUG: Executing ES Search Template '{template_id}' with params: {es_params}")
            try:
                response = await es.search_template(
                    index=index,
                    body={
                        "id": template_id,
                        "params": es_params
                    }
                )
            except Exception as template_err:
                print(f"Template execution failed [{template_id}], falling back to Python-built query: {template_err}")
                legacy_query = self._build_hybrid_query(analysis_result)
                response = await es.search(index=index, body=legacy_query)

            result_hits = [hit["_source"] for hit in response["hits"]["hits"]]
            total_count = response["hits"]["total"]["value"]
        
        # 4. Process Aggregations (Top Symptoms)
        top_symptoms = []
        if analysis_result["route"] == "rdb-path":
            from collections import Counter
            symptom_counter = Counter()
            for hit in result_hits:
                sym_nm = hit.get("SYM_NM") or hit.get("MAP_DESC_NAME") or hit.get("MAP_ITMNM_NAME")
                if sym_nm:
                    symptom_counter[sym_nm] += 1
            top_symptoms = [{"symptom": k, "count": v} for k, v in symptom_counter.most_common(10)]
        elif "response" in locals() and "aggregations" in response:
            buckets = response["aggregations"]["top_symptoms"]["buckets"]
            top_symptoms = [{"symptom": b["key"], "count": b["doc_count"]} for b in buckets]

        # 결과에서 벡터 데이터 제외 (가독성 및 응답 크기 최적화)
        for hit in result_hits:
            if isinstance(hit, dict):
                hit.pop("content_vector", None)
                hit.pop("symptom_vector", None)

        # 5. Skip LLM Natural Language Answer Generation (Delegated to Chatbot Engine)
        answer = ""
        
        result = {
            "intent": intent,
            "route": analysis_result["route"],
            "parameters": params,
            "answer": answer, # 자연어 답변 제거 (챗봇 엔진에서 포맷팅)
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

        print(f"\n✨ [Execution Completed]: Route: '{analysis_result['route']}' | Intent: '{intent}' | Source: '{analysis_result.get('source', 'unknown')}' | Total Records: {total_count}")
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
