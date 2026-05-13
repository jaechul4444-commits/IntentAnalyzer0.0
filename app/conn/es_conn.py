import os
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

load_dotenv()

class ElasticsearchClient:
    def __init__(self):
        self.host = os.getenv("ES_HOST", "http://localhost:9200")
        self.user = os.getenv("ES_USER")
        self.password = os.getenv("ES_PASSWORD")
        self.client = None

    async def connect(self):
        if not self.client:
            self.client = AsyncElasticsearch(
                self.host,
                basic_auth=(self.user, self.password) if self.user and self.password else None,
                verify_certs=False
            )
        return self.client

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None

es_client = ElasticsearchClient()

async def get_es_client():
    return await es_client.connect()
