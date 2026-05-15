import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def check_db():
    load_dotenv()
    dsn = os.getenv("PG_DSN")
    
    if not dsn:
        print("Error: PG_DSN not found in .env file.")
        return

    try:
        conn = await asyncpg.connect(dsn)
        
        # 1. List all tables
        print("\n--- [ Tables in Database ] ---")
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        for record in tables:
            print(f"- {record['table_name']}")

        # 2. Show structure of user_query_logs
        print("\n--- [ Structure of 'user_query_logs' ] ---")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_query_logs'
            ORDER BY ordinal_position
        """)
        for col in columns:
            print(f"{col['column_name']:20} | {col['data_type']:20} | Nullable: {col['is_nullable']}")

        # 3. Check TOP 10 rows
        try:
            claim_top10 = await conn.fetch("SELECT * FROM claim_symptoms LIMIT 10")
            print(f"\nTOP 10 rows in 'claim_symptoms': {claim_top10}")
        except Exception as e:
            print(f"\nCould not fetch from 'claim_symptoms': {e}")

        # 4. Check TOP 10 rows
        log_top10 = await conn.fetch("SELECT id, query_text, predicted_intent, left(query_vector::text, 50) as vector_preview FROM user_query_logs LIMIT 10")
        print(f"\nTOP 10 rows in 'user_query_logs': {log_top10}")

        # 5. Check row count
        count = await conn.fetchval("SELECT COUNT(*) FROM user_query_logs")
        print(f"\nTotal rows in 'user_query_logs': {count}")
        
        await conn.close()
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
