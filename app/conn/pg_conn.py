import os
import asyncpg
import json
from dotenv import load_dotenv

load_dotenv()

class PostgresClient:
    def __init__(self):
        self.pool = None
        self.dsn = os.getenv("PG_DSN")

    async def connect(self):
        if not self.dsn:
            print("WARNING: PG_DSN is not set in .env. PostgreSQL logging will be disabled.")
            return

        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self.dsn,
                    min_size=1,
                    max_size=10
                )
                print("Successfully connected to PostgreSQL.")
            except Exception as e:
                print(f"WARNING: Failed to connect to PostgreSQL: {e}")
                self.pool = None

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def save_query_log(self, query_text, tokens, token_list, intent, parameters, query_vector=None):
        """
        사용자 질의 및 토큰 데이터를 PostgreSQL에 저장합니다.
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_query_logs (
                    query_text, tokens, token_list, predicted_intent, extracted_parameters, query_vector
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                query_text,
                json.dumps(tokens),
                token_list,
                intent,
                json.dumps(parameters),
                query_vector
            )

    async def find_similar_log(self, query_text):
        """
        기존 로그에서 동일하거나 매우 유사한 질의가 있는지 검색합니다.
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            # 완전 일치 검색 (가장 빠름)
            row = await conn.fetchrow(
                "SELECT predicted_intent, extracted_parameters, query_vector FROM user_query_logs WHERE query_text = $1 LIMIT 1",
                query_text
            )
            if row:
                return {
                    "intent": row["predicted_intent"],
                    "parameters": json.loads(row["extracted_parameters"]),
                    "embedding": row["query_vector"]
                }
        return None

    async def execute_select_query(self, sql: str, params: list = None):
        """
        PostgreSQL 데이터베이스에서 읽기 전용 SELECT 쿼리를 안전하게 실행합니다.
        (insert, delete, update, merge 등 데이터 변경 쿼리는 절대 유입되지 못하도록 검증합니다.)
        """
        forbidden = ["insert", "delete", "update", "merge", "create", "drop", "alter", "truncate", "grant", "revoke"]
        clean_sql = sql.strip().lower()
        
        # 주석 제거 후 select 혹은 with로 시작하는지 재검증
        normalized_sql = clean_sql
        while normalized_sql.startswith("/*") or normalized_sql.startswith("--"):
            if normalized_sql.startswith("/*"):
                end_idx = normalized_sql.find("*/")
                if end_idx != -1:
                    normalized_sql = normalized_sql[end_idx+2:].strip()
                else:
                    break
            elif normalized_sql.startswith("--"):
                nl_idx = normalized_sql.find("\n")
                if nl_idx != -1:
                    normalized_sql = normalized_sql[nl_idx+1:].strip()
                else:
                    break

        if not (normalized_sql.startswith("select") or normalized_sql.startswith("with")):
            raise ValueError("Only SELECT or WITH queries are permitted on this route.")
            
        for f in forbidden:
            import re
            pattern = re.compile(rf"\b{f}\b")
            if pattern.search(clean_sql):
                raise ValueError(f"Unauthorized operation '{f}' detected in the query. Only read-only queries are allowed.")
                
        if not self.pool:
            await self.connect()
            
        if not self.pool:
            raise ConnectionError("PostgreSQL database connection pool is not available.")
            
        async with self.pool.acquire() as conn:
            if params:
                rows = await conn.fetch(sql, *params)
            else:
                rows = await conn.fetch(sql)
            return [dict(row) for row in rows]

pg_client = PostgresClient()

