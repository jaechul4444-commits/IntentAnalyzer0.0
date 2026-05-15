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

pg_client = PostgresClient()
