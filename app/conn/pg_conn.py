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
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=1,
                max_size=10
            )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def save_query_log(self, query_text, tokens, token_list, intent, parameters):
        """
        사용자 질의 및 토큰 데이터를 PostgreSQL에 저장합니다.
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_query_logs (
                    query_text, tokens, token_list, predicted_intent, extracted_parameters
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                query_text,
                json.dumps(tokens),
                token_list,
                intent,
                json.dumps(parameters)
            )

pg_client = PostgresClient()
