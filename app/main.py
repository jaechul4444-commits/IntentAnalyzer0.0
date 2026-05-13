import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.api.search import router as search_router
from app.conn.es_conn import es_client

class UnicodeJSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8" # 헤더에 utf-8 명시

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

app = FastAPI(title="Elastic Hybrid Search API", default_response_class=UnicodeJSONResponse)

@app.on_event("startup")
async def startup_event():
    await es_client.connect()

@app.on_event("shutdown")
async def shutdown_event():
    await es_client.close()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Vehicle Maintenance Search API is running"}

app.include_router(search_router)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
