import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def recent_claim():
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
        
        # 3. Check TOP 10 rows
        try:
            claim_top10 = await conn.fetch("SELECT * FROM claim_symptoms LIMIT 10")
            print(f"\nTOP 10 rows in 'claim_symptoms': {claim_top10}")
        except Exception as e:
            print(f"\nCould not fetch from 'claim_symptoms': {e}")

        # 4. Check TOP 10 rows
        log_top10 = await conn.fetch("SELECT * FROM user_query_logs LIMIT 10")
        print(f"\nTOP 10 rows in 'user_query_logs': {log_top10}")
        await conn.close()
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(recent_claim())
