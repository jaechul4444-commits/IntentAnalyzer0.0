import sys
import io

# Windows 콘솔 한글(CP949) 및 이모지 출력 시 인코딩 오류(UnicodeEncodeError) 방지 패치
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
        reload=False
    )

