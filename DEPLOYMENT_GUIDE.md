# Analyzer0.01 Docker 기반 리눅스 서버 배포 가이드

본 가이드는 **Docker**와 **Docker Compose**를 사용하여 **FastAPI**, **PostgreSQL**, **Elasticsearch (Nori 형태소 분석기 포함)**, **OpenAI API** 연동 애플리케이션을 리눅스 서버(Ubuntu 22.04 LTS 권장)에 원클릭으로 안전하고 신속하게 배포하기 위한 모든 단계를 안내합니다.

---

## 🚀 Docker 배포의 장점
1. **의존성 격리**: PostgreSQL, Elasticsearch, Python 가상환경 등을 서버에 직접 복잡하게 설치할 필요가 없습니다.
2. **Nori 플러그인 빌드 자동화**: Elasticsearch 기동 시 한국어 형태소 분석기(Nori)가 이미 포함된 이미지를 자동 빌드하여 플러그인 설치 실패 오류를 사전에 예방합니다.
3. **네트워크 통합**: 컨테이너 간의 네트워크 연결 및 Health Check가 자동으로 관리되므로 서비스 기동 순서가 보장됩니다.

---

## 1. 사전 준비 사항 (Prerequisites)

### A. 리눅스 서버 사양 권장안
* **OS**: Ubuntu 22.04 LTS 권장 (대부분의 Linux 배포판 호환)
* **사양**: 최소 **2 vCPU, 4GB RAM** 이상 (Elasticsearch 실행을 위해 **8GB RAM** 권장)
* **방화벽**: 외부 통신용 `80`(HTTP), `443`(HTTPS) 포트 오픈

### B. OpenAI API Key
* GPT-4o 및 임베딩 API(`text-embedding-3-small`) 호출이 가능한 유효한 OpenAI API Key

---

## 2. 서버 기초 설정 (Docker 권한 확인)

이미 Docker가 서버에 설치되어 있으므로 설치 과정은 건너뜁니다. 단, 일반 사용자 계정으로 로그인한 경우 매번 `sudo`를 붙여 실행하지 않도록 **사용자 그룹 권한**만 설정해 줍니다.

```bash
# 1. 현재 로그인한 계정을 docker 그룹에 등록 (sudo 권한 없이 docker 실행 가능하도록 설정)
sudo usermod -aG docker $USER

# 2. 변경된 권한 적용 (세션을 재접속하지 않고도 즉시 그룹 권한 적용)
newgrp docker

# 3. 정상 동작 및 버전 확인
docker --version
docker compose version
```

---


## 3. 애플리케이션 다운로드 및 설정

### Step 1. 소스 코드 가져오기 (Git Clone)
```bash
cd /var/www
sudo git clone https://github.com/your-repo/Analyzer0.01.git
sudo chown -R $USER:$USER /var/www/Analyzer0.01
cd /var/www/Analyzer0.01
```

### Step 2. 환경 변수(`.env`) 설정
도커 컴포즈 실행 시 환경 변수를 컨테이너로 전달하기 위해 `.env` 파일을 작성합니다.
```bash
cp .env.example .env
nano .env
```

**⚠️ Docker 배포 시 반드시 기입해야 하는 환경변수 설정:**
```ini
# OpenAI Settings (본인의 실제 API Key 입력)
OPENAI_API_KEY=sk-proj-YOUR_ACTUAL_OPENAI_API_KEY
OPENAI_MODEL_GPT=gpt-4o
OPENAI_MODEL_EMBEDDING=text-embedding-3-small

# App Settings
DEBUG=false
PORT=8000

# [참고] Docker Compose 네트워크 내부용 주소는 docker-compose.yml 내부에서 자동 덮어쓰기되므로
# 호스트 PC에서 개발/디버깅용 주소는 기본 상태로 그대로 두셔도 됩니다.
ES_HOST=http://localhost:9200
PG_DSN=postgresql://postgres:password@localhost:5432/intent_db
```

### ⚠️ [중요] 89번(FastAPI 앱) & 99번(Elasticsearch) 분리 서버 환경 배포 주의사항

배포하려는 서버가 **89번 서버(애플리케이션)**이고, Elasticsearch는 이미 **99번 서버**에 따로 구축되어 가동 중인 경우, 아래 세팅 및 방화벽 규칙을 반드시 사전에 적용하셔야 정상 연동됩니다.

#### 1. 89번 서버의 `.env` 환경 변수 수정
89번 서버의 `.env` 파일 내 `ES_HOST` 주소를 **99번 서버의 IP**로 변경합니다.
```ini
ES_HOST=http://<99번_서버_IP>:9200
```

#### 2. 89번 서버의 `docker-compose.yml` 리소스 최적화 수정
89번 서버에서는 로컬 Elasticsearch 컨테이너를 구동할 필요가 전혀 없으므로 다음과 같이 주석 처리/삭제합니다:
* **의존성 제거**: `web` 서비스 내부 `depends_on` 목록에서 `elasticsearch:` 하위 2개 라인을 주석 처리 또는 삭제합니다.
* **환경 변수 오버라이드 해제**: `web` 서비스 내부 `environment`의 `ES_HOST` 라인을 주석 처리하여 `.env`에 정의한 99번 서버 주소가 컨테이너 내부에 자연스럽게 로드되도록 합니다.
* **서버 자원 절약**: 파일 맨 아래에 정의된 `elasticsearch:` 서비스 블록 전체와 `volumes:` 내부의 `esdata:` 지정을 삭제하거나 주석 처리하여 89번 서버의 불필요한 메모리/디스크 낭비를 막아줍니다.

#### 3. 99번 서버(Elasticsearch)의 네트워크 및 포트 개방 설정
89번 서버에서 99번 서버의 ES 서비스로 통신이 가능해야 합니다:
* **방화벽 설정**: 99번 서버의 방화벽(UFW 또는 보안그룹)에서 **89번 서버의 IP**에 대해 **`9200` 포트(인바운드)를 허용**해 줍니다.
  ```bash
  # 99번 서버(Ubuntu)의 UFW 예시
  sudo ufw allow from <89번_서버_IP> to any port 9200 proto tcp
  ```
* **네트워크 바인딩 주소 검증**: 99번 서버의 `/etc/elasticsearch/elasticsearch.yml` 파일 내에 `network.host` 설정이 `127.0.0.1`로 묶여 있다면, 외부 접근이 불가능합니다. 이를 사설 IP 주소 또는 `0.0.0.0`으로 지정해 주셔야 합니다.

#### 4. 99번 서버의 Nori 형태소 분석기 설치 유무 확인
99번 서버의 Elasticsearch에 **Nori(노리) 형태소 분석기 플러그인**이 이미 깔려 있어야 한글 의도 분석이 동작합니다.
* **설치 확인 (99번 서버에서 실행)**:
  ```bash
  curl -s http://localhost:9200/_nodes/plugins | grep analysis-nori
  ```
* **미설치 시 추가 방법 (99번 서버에서 실행)**:
  ```bash
  sudo /usr/share/elasticsearch/bin/elasticsearch-plugin install analysis-nori
  sudo systemctl restart elasticsearch
  ```

---

## 4. Docker Compose 빌드 및 실행

준비된 설정 파일을 바탕으로 전체 컨테이너를 백그라운드(`-d`)에서 빌드 및 구동합니다.

```bash
# 컨테이너 빌드 및 백그라운드 실행
docker compose up -d --build
```
> 이 명령어 한 번으로 **PostgreSQL 14**, **Nori가 설치된 Elasticsearch 8.8.0**, 그리고 **FastAPI 앱**이 순서대로 빌드되고 유기적으로 실행됩니다.

### 실행 상태 확인
```bash
# 구동 중인 컨테이너 목록 및 헬스 체크 상태 확인
docker compose ps
```
출력 결과의 `STATUS` 필드가 모두 `Up (healthy)` 혹은 `Up` 상태로 변할 때까지 대기합니다.

### 기동 로그 모니터링
```bash
# FastAPI 앱 로그 실시간 확인
docker compose logs -f web

# 전체 컨테이너 로그 확인
docker compose logs -f
```

---

## 5. 초기 인덱스 및 데이터베이스 테이블 생성

컨테이너가 안정적으로 구동되면, FastAPI 컨테이너 내부의 파이썬 스크립트를 호출하여 Elasticsearch 한국어(Nori) 분석 인덱스를 초기 생성해 줍니다.

```bash
# FastAPI 웹 컨테이너 내부의 인덱스 생성 스크립트 실행
docker compose exec web python scripts/create_nori_index.py
```
> [!NOTE]
> 위 스크립트가 성공적으로 수행되면 `claims_index` 및 `dtc_index`가 Nori 형태소 분석기 맵핑과 함께 자동으로 설정됩니다.

---

## 6. Nginx 리버스 프록시 및 SSL 설정 (보안 강화)

실제 서비스 운영 환경에서는 도커 컨테이너 포트(`8000`)를 외부에 직접 노출하는 것보다 리눅스 호스트의 **Nginx**를 통해 리버스 프록시 형태로 전달하고 **SSL(HTTPS)** 보안을 적용하는 것을 강력하게 권장합니다.

### A. Nginx 설치 및 리버스 프록시 설정
```bash
# Nginx 설치
sudo apt install nginx -y

# 사이트 설정 파일 생성
sudo nano /etc/nginx/sites-available/analyzer
```

설정 파일 구성 (보유한 도메인 주소로 입력):
```nginx
server {
    listen 80;
    server_name your-domain.com; # 연동할 도메인 주소 기입

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 설정 활성화 및 재시작
sudo ln -s /etc/nginx/sites-available/analyzer /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default # 기본 페이지 비활성화
sudo nginx -t # 설정 문법 검사
sudo systemctl restart nginx
```

### B. SSL 인증서 적용 (Certbot - Let's Encrypt)
```bash
# Certbot 설치
sudo apt install snapd -y
sudo snap install core; sudo snap refresh core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot

# SSL 자동 설정 및 적용
sudo certbot --nginx -d your-domain.com
```

---

## 7. 컨테이너 일상 관리 치트시트

* **컨테이너 정지 및 유지**:
  ```bash
  docker compose stop
  ```
* **컨테이너 시작 (이전 상태 유지)**:
  ```bash
  docker compose start
  ```
* **서비스 종료 및 네트워크 삭제 (데이터 유지)**:
  ```bash
  docker compose down
  ```
* **데이터 완전 초기화 및 리셋 (DB 및 ES 볼륨 영구 삭제 - 주의!)**:
  ```bash
  docker compose down -v
  ```
* **소스 코드가 수정되어 앱만 재빌드하여 재구동할 때**:
  ```bash
  docker compose up -d --no-deps --build web
  ```
