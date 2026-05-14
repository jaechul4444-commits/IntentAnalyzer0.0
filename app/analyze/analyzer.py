import re
from app.llm.openai_service import openai_service
from app.utils.date_parser import parse_date_range
from app.utils.token_service import get_nori_tokens
from app.conn.pg_conn import pg_client

class IntentAnalyzer:
    def __init__(self):
        # DTC pattern: 1 letter followed by 4 digits (e.g., P2261)
        self.dtc_pattern = re.compile(r'[PBUC]\d{4}')

    async def analyze(self, query: str):
        # 1. Fast-Path: Check for DTC codes
        dtc_match = self.dtc_pattern.search(query.upper())
        if dtc_match:
            dtc_code = dtc_match.group()
            return {
                "route": "fast-path",
                "intent": "dtc_analysis",
                "parameters": {
                    "dtc_code": dtc_code
                }
            }

        # 2. Slow-Path: LLM extraction
        llm_data = await openai_service.extract_parameters(query)
        
        # Post-process date
        start_date, end_date = parse_date_range(llm_data.get("date_info"))
        
        # Generate embedding for hybrid search
        embedding = await openai_service.get_embedding(query)

        intent = llm_data.get("intent", "similar_case")
        parameters = {
            "symptom": llm_data.get("symptom"),
            "model": llm_data.get("model"),
            "start_date": start_date,
            "end_date": end_date
        }

        # 3. Nori Tokenization & PostgreSQL Logging
        try:
            tokens, token_list = await get_nori_tokens(query)
            await pg_client.save_query_log(
                query_text=query,
                tokens=tokens,
                token_list=token_list,
                intent=intent,
                parameters=parameters
            )
        except Exception as e:
            print(f"Logging Error: {e}")

        return {
            "route": "slow-path",
            "intent": intent,
            "parameters": parameters,
            "embedding": embedding
        }

analyzer = IntentAnalyzer()
