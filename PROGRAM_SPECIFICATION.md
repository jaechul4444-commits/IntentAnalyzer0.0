# 프로그램 정의서 (Program Specification)

**프로젝트 명**: Elastic Hybrid Search 기반 의도 분석 및 정비 데이터 검색 시스템  
**시스템 버전**: v1.5  
**작성일**: 2026-05-20  
**상태**: 최종 승인 (Production Ready)

---

## 1. 개요 (Overview)

본 시스템은 대규모 차량 정비 데이터(Claims) 및 고장코드(DTC) 정보를 초고속으로 탐색하고 정밀 분석하기 위해 설계된 **엔터프라이즈급 하이브리드 검색 및 의도 분석 엔진**입니다.

단순 키워드 매칭(Lexical Search)의 한계를 극복하고, 사용자의 자연어 질의에서 **의도(Intent)**와 **상세 파라미터(Slot-Filling)**를 지능적으로 추출하여, 구조화된 필터링 및 **의미론적 벡터 유사도 검색(Semantic Search)**을 결합한 하이브리드 쿼리를 수행합니다. 

### 1.1. 주요 비즈니스 가치
* **정비 프로세스 효율성 제고**: 현장 정비사가 입력하는 비정형 질문을 해석하여 가장 유사한 과거 정비 성공 사례와 조치 내역을 즉시 제공합니다.
* **통계적 통찰력 제공**: 특정 기간 동안 빈번하게 발생한 고장 부품 및 증상에 대해 순위와 추이를 시각화할 수 있는 집계 데이터(Aggregations)를 실시간으로 연산합니다.
* **비용 최적화 및 안정성 보장**: LLM API 호출 횟수를 최소화하기 위해 **PostgreSQL 캐싱 레이어** 및 **Aho-Corasick 기반 템플릿 우회 엔진**을 구축하여 API 비용을 절감하고 장애 시 안정적인 Fallback을 보장합니다.

---

## 2. 시스템 아키텍처 및 데이터 흐름 (System Architecture & Data Flow)

시스템은 질의의 성격에 따라 최적의 처리 속도와 비용을 보장하는 **다중 경로 파이프라인 (Multi-path Pipeline)**을 채택하고 있습니다.

### 2.1. 전체 데이터 흐름도

```mermaid
flowchart TD
    classDef pg fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef es fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef llm fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef core fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px;
    classDef target fill:#e0f7fa,stroke:#00acc1,stroke-width:2px;

    User(["사용자 자연어 질의 입력"]) --> Service["search_service.search"]
    Service --> Analyzer["analyzer.analyze"]

    %% 1단계: RDB 규칙 필터
    Analyzer --> RDBRule{1. RDB 규칙 체크<br>VIN 패턴 / RDB 키워드}:::core
    RDBRule -- "적중 (비용 0)" --> RDB_Direct["RDB-Path: PostgreSQL 조회"]:::target

    %% 2단계: 캐시 레이어
    RDBRule -- "미적중" --> CheckPGCache{"2. PG 로그 캐시 조회"}:::pg
    CheckPGCache -- "동일/유사 질의 존재" --> ReturnPGCache["PG 캐시된 의도 및 파라미터 반환"]:::pg
    ReturnPGCache --> ESQueryExec

    %% 3단계: Fast-Path
    CheckPGCache -- "신규 질의" --> CheckDTC{"3. DTC 코드 패턴 매칭 <br> [PBUC]\d{4}"}:::core
    CheckDTC -- "DTC 포함 (Fast-Path)" --> DTCService["DTC 상세 조회 및 동적 LLM 사전화"]:::es
    DTCService --> ReturnDTC["DTC 결과 즉시 반환"]
    ReturnDTC --> FinalSummary

    %% 4단계: Slow-Path: Template
    CheckDTC -- "일반 질의" --> TemplateEngine{"4. 템플릿 엔진 자동 분류"}:::core
    TemplateEngine -- "정적/동적 키워드 존재 <br> & 의도 트리거 매칭" --> ExecuteTemplate["Aho-Corasick & Regex 기반 <br> 파라미터 추출"]:::core
    ExecuteTemplate --> TokenizeQuery1["Nori 형태소 분석 및 PG 로깅"]:::pg
    TokenizeQuery1 --> ESQueryExec

    %% 5단계: Slow-Path: LLM
    TemplateEngine -- "키워드 미매칭 또는 모호함" --> LLMParser["5. OpenAI GPT-4o 파라미터 추출"]:::llm
    LLMParser --> TokenizeQuery2["Nori 형태소 분석 및 PG 로깅"]:::pg
    LLMParser -.->|OpenAI API 장애| FallbackEngine["6. Fallback 키워드 파서"]:::core
    FallbackEngine --> TokenizeQuery2
    
    %% LLM Structured Routing (Option C)
    LLMParser -- "search_type == 'structured' <br> (시맨틱 정형 요청)" --> RDB_Direct
    
    %% 임베딩 및 ES 하이브리드 쿼리
    LLMParser -- "search_type == 'semantic'" --> EmbedGen["text-embedding-3-small <br> 1536차원 벡터 생성"]:::llm
    EmbedGen --> ESQueryExec
    FallbackEngine -.->|Zero Vector| ESQueryExec

    %% ES 하이브리드 검색 및 답변 생성
    ESQueryExec["7. Elasticsearch 하이브리드 검색 <br> BM25 + kNN"]:::es
    ESQueryExec --> ES_Agg["상위 증상 통계 집계 Aggregation"]:::es
    ESQueryExec --> FinalSummary

    %% RDB 실행 및 스키마 폴백
    RDB_Direct --> RDBSchemas{DB 스키마 존재 여부}:::target
    RDBSchemas -- "존재 (PQMLIB)" --> RDB_Complex["대형 JOIN 쿼리 실행"]:::target
    RDBSchemas -- "부재" --> RDB_Fallback["public.hqm_csrs1000 단일 테이블 폴백"]:::target
    
    %% Final Answer Summarization (제거됨: 챗봇 엔진으로 이관)
    ES_Agg --> FinalSummary["빠른 JSON 직렬화 (LLM 응답 합성 배제)"]:::target
    RDB_Complex --> FinalSummary
    RDB_Fallback --> FinalSummary
    
    FinalSummary --> PG_Log["PG user_query_logs 로그 저장"]:::pg
    PG_Log --> FinalResult(["최종 JSON 결과 반환 (챗봇 엔진에서 렌더링)"])

    %% 키워드 동적 동기화
    ESQueryExec -.->|주기적 / 최초 1회| DynamicSync["ES Term Aggregations 기반 <br> Aho-Corasick 키워드 사전 업데이트"]:::es
```


---

## 3. 디렉토리 및 모듈별 역할 (Directory & Module Breakdown)

본 프로젝트는 모듈화 및 관심사 분리(SoC) 원칙에 따라 설계되어 유지보수성과 확장성이 우수합니다.

```
Analyzer0.01/
├── app/
│   ├── analyze/
│   │   └── analyzer.py         # Aho-Corasick 사전 구축, 패턴 매칭 및 라우팅 결정 (IntentAnalyzer)
│   ├── api/
│   │   └── search.py           # FastAPI 엔드포인트 정의 및 예외 처리
│   ├── conn/
│   │   ├── es_conn.py          # Elasticsearch 비동기 커넥션 관리 (AsyncElasticsearch)
│   │   └── pg_conn.py          # PostgreSQL asyncpg 커넥션 풀 구축 및 질의 로그 관리
│   ├── llm/
│   │   └── openai_service.py   # GPT-4o 파라미터 추출, 임베딩 생성 및 답변 요약 서비스
│   ├── service/
│   │   └── search_service.py   # 검색 파이프라인 제어, ES 검색 템플릿 연동 및 통계 집계
│   ├── utils/
│   │   ├── date_parser.py      # 자연어 날짜 표현을 'YYYYMMDD' 범위로 변환하는 유틸리티
│   │   └── token_service.py    # 한국어 형태소 분석기 Nori 토크나이저 연동 모듈
│   └── main.py                 # FastAPI 인스턴스 기동 및 데이터베이스 이벤트 루프 설정
├── scripts/
│   ├── init_db.py              # PostgreSQL 테이블 스키마 생성 및 초기화 스크립트
│   ├── create_nori_index.py    # Elasticsearch claims Nori 분석기 인덱스 생성 스크립트
│   ├── check_db.py             # PostgreSQL 연결 및 데이터 정합성 검증 스크립트
│   ├── check_mapping.py        # Elasticsearch 매핑 설정 유효성 검증
│   ├── get_index_details.py    # 원본 Elasticsearch 인덱스 속성 및 메타데이터 백업 스크립트
│   └── recent_search_data.py   # 최근 검색 패턴 모니터링 스크립트
├── requirements.txt            # 의존성 패키지 정의서
├── test.http                   # REST Client용 API 시나리오 테스트 파일
└── PROGRAM_SPECIFICATION.md    # [본 문서] 프로그램 정의서
```

---

## 4. 데이터베이스 및 인덱스 상세 설계 (Database & Index Design)

### 4.1. PostgreSQL: 사용자 질의 로그 및 캐시 (`user_query_logs`)
사용자가 입력한 검색어의 히스토리를 추적하고 캐싱하여 시스템의 재사용성을 높이고 형태소 정보를 영구 저장합니다.

* **테이블 명**: `user_query_logs`

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PRIMARY KEY` | 고유 식별자 고정 일련번호 |
| `query_text` | `TEXT` | `NOT NULL` | 사용자가 입력한 오리지널 자연어 질의 |
| `tokens` | `JSONB` | - | Nori 형태소 분석 결과 객체 리스트 (JSON 형식) |
| `token_list` | `TEXT[]` | - | 검색 속도 최적화를 위해 문자열 배열 형태로 풀어낸 형태소 목록 |
| `predicted_intent` | `VARCHAR(100)`| - | 탐지된 의도 (`trend_analysis`, `similar_case` 등) |
| `extracted_parameters`| `JSONB` | - | 분석된 슬롯 파라미터 (`model`, `symptom`, `date_range` 등) |
| `query_vector` | `REAL[]` | - | `text-embedding-3-small`로 생성된 1536차원 Dense Vector |
| `created_at` | `TIMESTAMPTZ`| `DEFAULT NOW()`| 로그 생성 일시 (KST 시간대 자동 저장) |

> [!NOTE]
> `query_text` 필드에는 B-Tree 인덱스가 기본 탑재되어 신규 유저 질의가 들어왔을 때 캐시 존재 여부를 $O(log N)$의 복잡도로 판별합니다.

---

### 4.2. Elasticsearch: 정비 클레임 데이터 및 Nori 토크나이저 설정
대규모 비정형 텍스트 필드를 효율적으로 검색하기 위해 한글 형태소 분석기인 `nori_analyzer`를 적용하였습니다.

* **인덱스 명**: `jjc_claim_nori_v1` (환경 변수 `ES_INDEX_CLAIMS`에 따름)
* **분석기 구성 (Settings)**:
```json
{
  "analysis": {
    "analyzer": {
      "nori_analyzer": {
        "type": "custom",
        "tokenizer": "nori_tokenizer",
        "decompound_mode": "mixed",
        "filter": ["nori_readingform", "lowercase"]
      }
    },
    "tokenizer": {
      "nori_tokenizer": {
        "type": "nori_tokenizer",
        "decompound_mode": "mixed"
      }
    }
  }
}
```

* **핵심 필드 매핑 세부 사항 (Properties)**:

| 필드명 | 데이터 타입 | 분석기/포맷 | 설명 |
| :--- | :--- | :--- | :--- |
| `상세내용` | `text` | `nori_analyzer` | 차량의 구체적인 고장 고지 및 정비 상세 텍스트 (BM25 타겟) |
| `상세내용.keyword`| `keyword` | - | 통계 분석 집계(`aggregations`)를 위한 키워드 서브필드 |
| `차종` | `text` / `keyword` | `nori_analyzer` / - | 대상 차량 모델명 (정밀 필터링 및 집계 용도) |
| `부품명` | `text` / `keyword` | `nori_analyzer` / - | 교체 또는 진단된 핵심 부품명 |
| `현상` | `text` / `keyword` | `nori_analyzer` / - | 정비 접수 시 등록된 증상 코드 및 명칭 |
| `확정일자` | `date` | `yyyyMMdd` | 차량 수리가 완료되어 확정된 일자 (필터용) |
| `content_vector` | `dense_vector`| `dims: 1536` | 정비 상세 내용의 의미 정보를 담은 고차원 벡터 (kNN 유사도 비교 타겟) |

---

## 5. 핵심 기능 및 알고리즘 설계 (Core Pipelines & Algorithms)

### 5.1. Fast-Path: DTC 코드 신속 검색 파이프라인
사용자의 질의에서 표준 고장코드 패턴(예: `P2261`, `C1612` 등)이 탐지되면 즉각적으로 실행되는 고속 응답 파이프라인입니다.

1. **정규식 매칭**: `r'[PBUC]\d{4}'` 정규식을 활용해 질의어에서 고장코드를 추출합니다.
2. **DTC 전용 인덱스 조회**: `dtc_index`에서 검색 템플릿 `dtc_analysis_template`을 활용하여 해당 코드의 상세 내용을 즉각 검색합니다.
3. **LLM 동적 온디맨드 사전화 (Fallback & Auto-index)**:
   * 만약 인덱스에 데이터가 존재하지 않는 신규 DTC 코드인 경우, `openai_service.get_dtc_details`를 호출하여 DTC의 상세 설명(description)과 흔한 원인(cause)을 생성합니다.
   * 생성된 데이터는 향후 속도 개선을 위해 즉시 Elasticsearch `dtc_index`에 저장하고 클라이언트에 반환합니다.

---

### 5.2. PostgreSQL 캐시 및 pgvector 유사성 분석
동일하거나 매우 유사한 질의 패턴의 재입력 시 성능을 $O(1)$로 보장하며 불필요한 LLM 비용을 완전히 상쇄하는 레이어입니다.

```python
# app/conn/pg_conn.py
async def find_similar_log(self, query_text):
    async with self.pool.acquire() as conn:
        # 완전 일치하는 캐시 레코드가 있을 경우 즉각 튜플 정보 복원
        row = await conn.fetchrow(
            "SELECT predicted_intent, extracted_parameters, query_vector FROM user_query_logs WHERE query_text = $1 LIMIT 1",
            query_text
        )
        if row:
            return {
                "intent": row["predicted_intent"],
                "parameters": json.loads(row["extracted_parameters"]),
                "embedding": row["query_vector"]
            }
    return None
```

---

### 5.3. Aho-Corasick 기반 템플릿 우회 엔진 및 키워드 동적 업데이트
사전 정의된 자연어 형태의 정비 질문이 들어왔을 때, 고비용의 LLM 호출을 완전히 바이패스(Bypass)하기 위한 고성능 오토마타 구조입니다.

#### 키워드 동적 추출 및 동기화 메커니즘
서버 구동 시 또는 검색 수행 시 최초 1회, **Elasticsearch의 실제 데이터 집계 정보**를 분석하여 키워드 매칭 사전을 자동으로 구축합니다.

*   **환경 변수 로딩 안정성 확보**: `analyzer.py` 내부에서 `dotenv.load_dotenv()`를 독립적으로 실행하여 메인 클레임 데이터 인덱스 환경설정을 확실하게 탐색합니다.
*   **실데이터 인덱스 기본 폴백**: 데이터가 없는 빈 인덱스 참조 현상을 원천 차단하기 위해, 실제 **45,713건**의 문서가 들어있는 **`jjc_20260518_claim_test_index`**를 최우선 Fallback 인덱스로 고정하여 데이터 정합성을 항시 유지합니다.
*   **Path Guard (개발자 디바그 사용성 개선)**: 단독 파일 실행 시 `ModuleNotFoundError: No module named 'app'` 에러를 차단할 수 있도록 `sys.path` 자동 보정 코드를 도입하여 독립적 구동 및 테스트 편의성을 보장합니다.


```mermaid
sequenceDiagram
    participant App as IntentAnalyzer (App)
    participant ES as Elasticsearch Index
    
    App->>ES: Terms Aggregation Query 요청 (차종, 부품, 현상 각 100건)
    ES-->>App: 유니크 키워드 목록 리턴
    Note over App: 기존 ahocorasick Automaton 재구성
    App->>App: 기본 하드코딩 키워드 적재
    App->>App: ES 동적 키워드 병합 및 add_word()
    App->>App: automaton.make_automaton() 컴파일 완료
```

#### 템플릿 의도 판단 로직
사용자가 질문에서 특정 의도 트리거(예: "가장 많이", "추이", "원인", "사례" 등)와 컴파일된 차종/증상 키워드를 조합하여 질문했을 때, LLM을 타지 않고 Regex와 Aho-Corasick 사전 조합만으로 슬롯 필링과 파라미터 매핑을 초고속 완료합니다.

---

### 5.4. Slow-Path: LLM 기반 파라미터 정제 및 Fallback 구조
템플릿 매칭에 잡히지 않는 비정형 자연어 질의는 LLM 파이프라인으로 전환되어 다각도로 해석됩니다.

* **OpenAI GPT-4o Parameter Extractor**:
  질의 분석을 통해 `symptom`, `model`, `date_info`를 식별하고 정밀한 의도(`intent`: `trend_prediction`, `cause_analysis` 등)와 통계 정렬 조건(`sort_order`)을 확정합니다.
* **OpenAI Quota Limit Fallback**:
  만약 OpenAI API 한도 초과(429 Error) 또는 연결 타임아웃 등의 장애가 발생하면, 시스템은 즉각 **Aho-Corasick 추출 결과와 시간 디폴트(2024.01.01 ~ 2026.12.31)**를 파라미터로 바인딩하여 비즈니스 가용성을 100% 유지합니다.

---

### 5.5. 하이브리드 검색 (BM25 + kNN k-최근접 이웃) 및 Mustache 검색 템플릿
분석된 의도와 파라미터는 Elasticsearch 상의 Mustache 템플릿(예: `trend_analysis_template`, `similar_case_template` 등)으로 바인딩되어 검색에 실립니다.

* **Mustache Search Template 연동**: 템플릿에 `query_vector`가 존재할 경우 아래와 같은 하이브리드 KNN 쿼리를 조합하여 실행합니다.

```json
{
  "query": {
    "bool": {
      "must": [
        { "range": { "확정일자": { "gte": "{{start_date}}", "lte": "{{end_date}}" } } }
      ],
      "should": [
        { "match": { "상세내용": "{{symptom}}" } }
      ]
    }
  },
  "knn": {
    "field": "content_vector",
    "query_vector": {{query_vector}},
    "k": 10,
    "num_candidates": 100
  },
  "aggs": {
    "top_symptoms": {
      "terms": {
        "field": "상세내용.keyword",
        "size": 10,
        "order": { "_count": "{{sort_order}}" }
      }
    }
  },
  "size": 10
}
```

---

## 6. API 명세 (API Specification)

### 6.1. 검색 통합 API (`POST /api/data/search`)

* **Endpoint**: `POST /api/data/search`
* **Request Header**: `Content-Type: application/json`
* **Request Body**:
```json
{
  "query": "사용자 질문 자연어 텍스트"
}
```

* **Response Body**:
```json
{
  "intent": "판단된 의도 (dtc_analysis | trend_analysis | cause_analysis | similar_case | trend_prediction)",
  "route": "처리 경로 (fast-path | slow-path | rdb-path)",
  "parameters": {
    "symptom": ["추출된 증상 목록"],
    "model": "추출된 차종 명",
    "sort_order": "asc 또는 desc",
    "start_date": "YYYYMMDD 형식 시작일",
    "end_date": "YYYYMMDD 형식 종료일"
  },
  "answer": "", // v1.5부터 제거됨 (챗봇 엔진에서 즉시 렌더링)
  "results": [
    {
      "차종": "그랜저 IG",
      "부품명": "엔진 댐퍼",
      "현상": "엔진 진동 및 소음",
      "상세내용": "엔진 댐퍼 풀리 유격으로 인한 진동 및 가속 불량 발생",
      "확정일자": "20250615"
    }
  ],
  "top_statistics": [
    {
      "symptom": "엔진 진동",
      "count": 42
    }
  ],
  "total": "매칭된 검색 결과 총 레코드 수",
  "source": "의도 분석 소스 (pg_cache | template_engine | llm_analysis | fallback)"
}
```

---

### 6.2. 대표적인 REST 클라이언트 요청/응답 예시

#### 예시 1: DTC 고장코드 검색 (Fast-Path)
* **Request**:
```json
{
  "query": "P2261 고장코드에 대해 설명해줘"
}
```
* **Response**:
```json
{
  "intent": "dtc_analysis",
  "route": "fast-path",
  "parameters": {
    "dtc_code": "P2261"
  },
  "answer": "",
  "results": [
    {
      "dtc_code": "P2261",
      "description": "Turbocharger Bypass Valve - Mechanical Malfunction",
      "cause": "솔레노이드 밸브 누설, 바이패스 제어 호스 손상, 밸브 고착"
    }
  ],
  "top_statistics": [],
  "total": 1,
  "source": "llm_analysis"
}
```

#### 예시 2: 차량 모델 통계/순위 질의 (Slow-Path - Template Engine 우회)
* **Request**:
```json
{
  "query": "최근 6개월간 그랜저 가장 많이 발생한 클레임 증상 알려줘"
}
```
* **Response**:
```json
{
  "intent": "trend_analysis",
  "route": "slow-path",
  "parameters": {
    "symptom": [],
    "model": "그랜저",
    "sort_order": "desc",
    "start_date": "20251118",
    "end_date": "20260518"
  },
  "answer": "",
  "results": [
    {
      "차종": "그랜저",
      "부품명": "가변 밸브 타이밍 센서",
      "현상": "엔진 부조 및 진동",
      "상세내용": "센서 오염에 의한 출력 부족 및 엔진 경동 유발",
      "확정일자": "20260212"
    }
  ],
  "top_statistics": [
    {
      "symptom": "엔진 부조 및 진동",
      "count": 18
    },
    {
      "symptom": "변속 충격",
      "count": 12
    }
  ],
  "total": 30,
  "source": "template_engine"
}
```

---

## 7. 설치 및 운영 가이드 (Installation & Operations Guide)

### 7.1. 시스템 필수 요구사양
* **Python**: 3.9 이상 권장
* **Database**:
  * PostgreSQL 12+ (로그 저장 및 유사도 질의 연산용)
  * Elasticsearch 8.x+ (Nori Morphological Analyzer 플러그인 탑재 필수)

### 7.2. 환경 변수 세팅 (`.env`)
```ini
PORT=8000
PG_DSN=postgresql://username:password@localhost:5432/dbname
ES_HOST=http://localhost:9200
ES_USER=elastic
ES_PASSWORD=elastic_password
ES_INDEX_CLAIMS=jjc_claim_nori_v1
ES_INDEX_DTC=dtc_index
ES_INDEX_LOGS=jjc_search_logs_index
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL_GPT=gpt-4o
OPENAI_MODEL_EMBEDDING=text-embedding-3-small
```

### 7.3. 서비스 배포 및 초기화 스크립트 실행 순서

1. **의존성 모듈 설치**:
   ```bash
   pip install -r requirements.txt
   ```
2. **PostgreSQL 스키마 초기화**:
   ```bash
   python scripts/init_db.py
   ```
3. **Elasticsearch Index 및 Nori 분석기 매핑 구축**:
   ```bash
   # 원본 Elasticsearch에서 mapping 세부사항을 index_info.json으로 백업합니다.
   python scripts/get_index_details.py
   
   # nori 형태소 분석기가 적용된 새로운 jjc_claim_nori_v1 인덱스를 생성합니다.
   python scripts/create_nori_index.py
   ```
4. **FastAPI 백엔드 서버 구동**:
   ```bash
   python app/main.py
   ```

---

## 8. 예외 처리 및 모니터링 수단 (Resilience & Monitoring)

1. **Elasticsearch 커넥션 다운**:
   ES 서버 불통 시, FastAPI의 exception handler를 거치며 클라이언트에게 500 에러를 전송하지 않고 HTTP 표준 응답 포맷에 맞춰 에러 세부 사항을 명확한 JSON 메시지로 반환하도록 래핑하고 있습니다.
2. **OpenAI Quota 한도 초과**:
   사용량이 폭주하여 OpenAI API가 에러를 발생시키는 경우, `openai_service`는 Aho-Corasick 정적 단어 매칭 및 사전 설정 기반으로 자동 전환(Soft-degradation)되어 시스템 무중단 검색을 영위합니다.
3. **독립 패키징 빌드**:
   `PyInstaller` 라이브러리를 통해 파이썬 가상환경 없이도 독립적으로 더블클릭 기동 가능한 싱글 바이너리(.exe) 파일 빌드가 완료되어, 복잡한 인프라가 배제된 현장 PC에도 직접 간편 배포가 가능합니다.

---

**[문서 끝]**
