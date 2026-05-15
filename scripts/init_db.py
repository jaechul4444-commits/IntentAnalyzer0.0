import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def init_db():
    load_dotenv()
    dsn = os.getenv("PG_DSN")
    
    if not dsn:
        print("Error: PG_DSN not found in .env file.")
        return

    try:
        print(f"Connecting to {dsn.split('@')[-1]}...")
        conn = await asyncpg.connect(dsn)
        
        # 1. Create table for user query logs
        print("Creating table 'user_query_logs'...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_query_logs (
                id SERIAL PRIMARY KEY,
                query_text TEXT,
                tokens JSONB,
                token_list TEXT[],
                predicted_intent TEXT,
                extracted_parameters JSONB,
                query_vector REAL[],
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        
        # Add column if table already exists without it
        await conn.execute("ALTER TABLE user_query_logs ADD COLUMN IF NOT EXISTS query_vector REAL[]")
        
        print("Success: Table 'user_query_logs' created or already exists.")
        await conn.close()
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(init_db())
