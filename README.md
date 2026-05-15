# 🚀 Elastic Hybrid Search 기반 의도 분석 및 정비 데이터 검색 API (v1.4)

차량 정비 데이터(Claims) 및 고장코드(DTC)를 분석하여 사용자 질의의 의도를 파악하고, **Aho-Corasick 동적 키워드 매칭**, **PostgreSQL 벡터 로그 캐싱**, 그리고 **LLM 기반 하이브리드 검색**을 결합하여 최상의 성능과 안정성을 제공하는 차세대 검색 시스템입니다.

---

## 1. 주요 업데이트 사항 (v1.4)

*   **동적 키워드 로딩**: 서비스 시작 시 Elasticsearch 인덱스에서 실제 데이터(차종, 부품명, 현상)를 추출하여 Aho-Corasick 오토마타를 자동으로 빌드합니다. (데이터 정합성 향상)
*   **고급 통계 정렬**: "가장 많은/적은"과 같은 사용자 의도에 따라 통계 집계 결과를 동적으로 정렬(ASC/DESC)합니다.
*   **PostgreSQL 벡터 캐싱**: 질의 임베딩을 저장하고 유사도 검색(`vector` 연산)을 통해 동일/유사 질의에 대해 OpenAI API 호출 없이 즉각 답변을 반환합니다.
*   **강화된 Fallback 로직**: OpenAI API 장애 또는 할당량 초과 시, 동적으로 로드된 키워드와 사전 정의된 규칙을 기반으로 검색을 자동 수행하여 서비스 연속성을 보장합니다.

---

## 2. 시스템 아키텍처 (Advanced Architecture)

본 시스템은 다단계 분석 파이프라인을 통해 효율적으로 질의를 처리하며, 장애 발생 시 자동으로 Fallback 로직을 가동합니다.

:::mermaid
graph TD
    User([사용자 질의]) --> Cache{PG 로그 캐시 확인}
    Cache -- "유사 질의 (벡터 유사도)" --> Response
    Cache -- "신규 질의" --> FastPath{Fast-Path: Regex}
    
    subgraph "Hybrid Analysis"
        FastPath -- "DTC 패턴 매칭" --> DTC_Search
        FastPath -- "일반 질의" --> AC_Match[Aho-Corasick 동적 키워드 추출]
        AC_Match --> LLM_Extract[LLM 의도/파라미터 추출 & 임베딩 생성]
        LLM_Extract --> Date_Parser[날짜 전처리/변환]
    end
    
    subgraph "Elasticsearch"
        DTC_Search --> ES[(Elasticsearch)]
        Date_Parser --> Hybrid_Search[Hybrid Search: BM25 + kNN]
        Hybrid_Search --> ES
    end
    
    ES --> Log_Save[PG 벡터 로그 저장]
    Log_Save --> Response([최종 결과 반환])
    
    %% Fallback Logic
    LLM_Extract -.->|OpenAI API Error| Fallback[Aho-Corasick Fallback Logic]
    Fallback --> Date_Parser
:::

---

## 3. 기술 스택 (Tech Stack)

| 구분 | 기술 | 주요 역할 |
| :--- | :--- | :--- |
| **Framework** | **FastAPI** | 비동기 API 엔드포인트 서빙 |
| **Database** | **Elasticsearch** | BM25 텍스트 검색 및 kNN 밀집 벡터 검색 |
| **Log DB** | **PostgreSQL** | 검색 로그 저장 및 **벡터 유사도 기반 질의 캐싱** |
| **Matching** | **Aho-Corasick** | **ES 데이터 기반 실시간 키워드 사전 업데이트** |
| **AI/LLM** | **OpenAI API** | GPT-4o (의도 분석), text-embedding-3-small (임베딩) |
| **Async I/O** | **Asyncpg / Aiohttp** | 데이터베이스 및 외부 API 비동기 통신 최적화 |

---

## 4. 핵심 기능 (Key Features)

### 4.1. 지능형 3단계 의도 분석
*   **Level 1 (Regex)**: 고장코드(DTC, 예: P2261) 패턴을 즉시 포착하여 고속 라우팅.
*   **Level 2 (Aho-Corasick)**: **Elasticsearch에서 실시간으로 로드된** 차종, 부품명 사전을 기반으로 밀리초(ms) 단위의 키워드 추출.
*   **Level 3 (LLM)**: GPT-4o를 통해 복잡한 문맥 파악, 상세 파라미터(증상, 날짜, 정렬 순서) 추출 및 벡터 생성.

### 4.2. 자연어 답변 생성 (Conversational AI)
*   **LLM 기반 요약**: 검색된 수많은 정비 로그를 분석하여, 사용자의 질문에 대한 핵심 답변을 자연스러운 한국어 문장으로 생성합니다.
*   **지식 합성**: 여러 사례에서 공통적으로 나타나는 원인이나 해결 방법을 종합하여 전문가 수준의 조언을 제공합니다.

### 4.3. 고급 통계 분석 (Smart Aggregation)
*   **동적 정렬 기능**: "가장 많은", "가장 적은" 등의 사용자 의도를 파악하여 통계 데이터를 오름차순(ASC) 또는 내림차순(DESC)으로 정렬하여 반환합니다.
*   **필드별 집계**: 증상(`현상`), 부품명 등을 기준으로 실시간 발생 빈도를 계산합니다.

### 4.4. 고성능 로그 캐싱 (Semantic Query Caching)
*   **PostgreSQL 벡터 검색**: `pgvector`를 활용하여 사용자의 신규 질의와 유사한 이전 질의가 있을 경우, DB에서 즉시 결과를 반환하여 OpenAI API 비용을 절감.
*   **학습 데이터 자동 축적**: 모든 분석 결과는 PostgreSQL에 저장되어 향후 모델 학습이나 통계 분석에 활용됩니다.

### 4.5. 견고한 장애 대응 (Robust Resilience)
*   OpenAI API 할당량 초과(429) 또는 네트워크 장애 시, **ES에서 추출된 키워드 기반의 Fallback 로직**으로 자동 전환되어 중단 없는 서비스를 제공합니다.

---

## 5. 디렉토리 구조 (Directory Structure)

```text
Analyer0.0/
├── app/
│   ├── api/          # FastAPI Router (search.py)
│   ├── analyze/      # IntentAnalyzer (Aho-Corasick + Regex + LLM)
│   ├── service/      # SearchService (ES Hybrid Query Builder)
│   ├── conn/         # DB Connection (es_conn.py, pg_conn.py)
│   ├── llm/          # OpenAI Service (Completion, Embedding)
│   ├── utils/        # Common Utilities (Date parsing, Tokenizing)
│   └── main.py       # API 앱 정의 및 Lifecycle 관리
├── scripts/          # 운영 스크립트 (create_nori_index.py, init_db.py, check_db.py 등)
├── main.py           # 전체 애플리케이션 진입점 (Uvicorn 실행)
├── test.http         # API 테스트용 HTTP 샘플
├── project_build.spec# PyInstaller 빌드 설정
├── requirements.txt  # 의존성 리스트
└── .env              # 설정 정보
```

---

## 6. 설치 및 시작하기 (Installation)

### 6.1. 환경 설정
1.  `.env.example` 파일을 복사하여 `.env` 파일을 생성합니다.
2.  `OPENAI_API_KEY`, `ES_HOST`, `PG_DSN` 등을 환경에 맞게 수정합니다.

### 6.2. 초기화 스크립트 실행
```bash
# 1. PostgreSQL 테이블 생성 (logs 테이블 및 pgvector 확장 필요)
python scripts/init_db.py

# 2. Elasticsearch 인덱스 및 매핑 설정 (Nori 분석기 포함)
python scripts/create_nori_index.py
```

### 6.3. 서비스 실행
```bash
python main.py
```
*   서버는 기본적으로 `http://localhost:8000`에서 실행됩니다.

---

## 7. API 사용법 (Usage)

### **POST /api/data/search**
하이브리드 분석 엔진을 통한 검색 결과를 반환합니다.

**Request Body (Example):**
```json
{
  "query": "1월에 가장 많이 발생한 아반떼 증상이 뭐야?"
}
```

**Response (Example):**
```json
{
  "route": "slow-path",
  "intent": "trend_analysis",
  "parameters": {
    "model": "아반떼",
    "sort_order": "desc",
    "start_date": "20260101",
    "end_date": "20260131"
  },
  "answer": "2026년 1월 아반떼 차량에서 가장 빈번하게 발생한 증상은 '엔진 진동'입니다...",
  "top_statistics": [
    {"symptom": "엔진 진동", "count": 45},
    {"symptom": "시동 불량", "count": 32}
  ],
  "source": "llm_analysis",
  "results": [...]
}
```

---

## 8. 빌드 (Build)

독립 실행형 파일(.exe)로 빌드하려면 다음 명령어를 사용합니다:
```bash
pyinstaller project_build.spec
```
빌드된 결과물은 `dist/` 폴더 내에 생성됩니다.
