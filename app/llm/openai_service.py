import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class OpenAIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.gpt_model = os.getenv("OPENAI_MODEL_GPT", "gpt-4o")
        self.embedding_model = os.getenv("OPENAI_MODEL_EMBEDDING", "text-embedding-3-small")

    async def extract_parameters(self, query: str):
        """
        Extract symptoms, model, and date from natural language query.
        """
        system_prompt = """
        You are an expert in vehicle maintenance data analysis. 
        Extract the following parameters from the user's query in JSON format:
        - symptom: list of symptoms or issues (e.g., ["engine vibration", "cold start"])
        - model: vehicle model name (e.g., "Grandeur IG")
        - date_info: natural language date description. 
          * CRITICAL: If the user mentions a month (e.g., "1월"), extract it here.
          * If they mention "last 6 months", "recently", "last year", extract it here.
        - intent: one of [cause_analysis, trend_analysis, similar_case, supplier_analysis, dtc_analysis]
        
        If a value is not found, use null.
        """
        
        response = await self.client.chat.completions.create(
            model=self.gpt_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    async def get_embedding(self, text: str):
        """
        Generate dense vector embedding for kNN search.
        """
        response = await self.client.embeddings.create(
            input=text,
            model=self.embedding_model
        )
        return response.data[0].embedding

    async def get_dtc_details(self, dtc_code: str):
        """
        Generate description and cause for a new DTC code.
        """
        system_prompt = "You are an automotive diagnostic expert. Provide a concise description and common causes for the given DTC code in JSON format with keys 'description' and 'cause'."
        response = await self.client.chat.completions.create(
            model=self.gpt_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"DTC Code: {dtc_code}"}
            ],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "dtc_code": dtc_code,
            "description": data.get("description"),
            "cause": data.get("cause")
        }

openai_service = OpenAIService()
