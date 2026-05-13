import uvicorn
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

if __name__ == "__main__":
    # 포트 설정 (기본값 8000)
    port = int(os.getenv("PORT", 8000))
    
    # app 디렉토리 내의 main.py의 app 객체를 실행
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=True
    )
