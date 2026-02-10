# Skyline API Server Extension 🚀

> **DCloud Platform을 위한 OpenStack 확장 API 서버**  
> OpenStack Skyline 기반의 현대적인 클라우드 관리 API 서버

---

## 📋 목차

- [프로젝트 소개](#-프로젝트-소개)
- [핵심 기능](#-핵심-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [빠른 시작](#-빠른-시작)
- [설정 가이드](#-설정-가이드)
- [API 문서](#-api-문서)
- [프로젝트 구조](#-프로젝트-구조)
- [개발 가이드](#-개발-가이드)
- [트러블슈팅](#-트러블슈팅)

---

## 🎯 프로젝트 소개

**Skyline API Server Extension**은 OpenStack Skyline을 기반으로 DCloud 플랫폼의 요구사항을 충족하기 위해 확장된 백엔드 API 서버입니다.

### 왜 이 프로젝트인가?

- **현대적인 아키텍처**: FastAPI 기반의 고성능 비동기 API
- **확장된 기능**: 표준 OpenStack API에 포트포워딩, 자동화, 모니터링 기능 추가
- **개발자 친화적**: Swagger UI 자동 생성, 명확한 에러 메시지
- **운영 효율성**: 한국어 활동 로그, 프로메테우스 메트릭 연동

### 기술 스택

```mermaid
graph LR
    A[Client] --> B[FastAPI]
    B --> C[OpenStack Services]
    B --> D[External APIs]
    B --> E[Database]
    
    C --> C1[Nova - 인스턴스]
    C --> C2[Cinder - 볼륨]
    C --> C3[Neutron - 네트워크]
    C --> C4[Keystone - 인증]
    
    D --> D1[Port Forwarding API]
    D --> D2[Prometheus]
    
    E --> E1[SQLite/MySQL]
```

| 계층 | 기술 |
|------|------|
| **Web Framework** | FastAPI 0.128+ |
| **ASGI Server** | Uvicorn (개발), Gunicorn (프로덕션) |
| **인증/보안** | python-jose (JWT), Keystone |
| **데이터베이스** | SQLAlchemy 2.0, Alembic (마이그레이션) |
| **OpenStack 클라이언트** | python-novaclient, python-cinderclient, python-neutronclient |
| **HTTP 클라이언트** | httpx (비동기) |
| **모니터링** | Prometheus, psutil |

---

## ✨ 핵심 기능

### 1️⃣ 인스턴스 관리 (Compute)

```
POST   /api/v1/instances          # 인스턴스 생성 (자동 SSH 포트포워딩 포함)
GET    /api/v1/instances/{id}     # 인스턴스 조회
DELETE /api/v1/instances/{id}     # 인스턴스 삭제
POST   /api/v1/instances/{id}/start    # 시작
POST   /api/v1/instances/{id}/stop     # 정지
POST   /api/v1/instances/{id}/reboot   # 재시작
POST   /api/v1/instances/{id}/console  # VNC 콘솔 URL
```

**특징:**
- ✅ 인스턴스 생성 시 **SSH 포트(22) 자동 포트포워딩**
- ✅ 서버 생성 시 볼륨 자동 생성 및 연결
- ✅ 모든 작업에 대한 **한국어 활동 로그** 기록

### 2️⃣ 볼륨 관리 (Block Storage)

```
GET    /api/v1/extension/volumes        # 볼륨 목록
DELETE /api/v1/volumes/{id}              # 볼륨 삭제
POST   /api/v1/instances/{id}/volumes/attach   # 볼륨 연결
POST   /api/v1/instances/{id}/volumes/detach   # 볼륨 분리
```

### 3️⃣ 포트포워딩 (외부 Proxy VM 연동) 🔌

**외부 포트포워딩 서비스와의 통합** - 가장 핵심적인 확장 기능!

```
POST   /api/v1/portforward              # 포트포워딩 규칙 생성
GET    /api/v1/portforward              # 규칙 목록 조회
GET    /api/v1/portforward/vm/{vm_id}   # VM별 규칙 조회
PATCH  /api/v1/portforward/{rule_id}    # 규칙 수정
DELETE /api/v1/portforward/{rule_id}    # 규칙 삭제
```

**특징:**
- 🌐 외부 Proxy VM의 포트포워딩 API와 HTTP 통신
- 🔐 인스턴스 생성 시 SSH(22번 포트) 자동 포트포워딩
- 📊 Floating IP 상태 및 포트 할당 미리보기
- 🔄 인스턴스 삭제 시 관련 포트포워딩 자동 정리

**구성:**
```yaml
default:
  database_url: mysql://user:pass@localhost/skyline

openstack:
  keystone_url: http://keystone:5000/v3
  portforward_api_url: http://proxy-vm:8080/api/v1  # 포트포워딩 API
  portforward_authorization_key: your-secret-key-here  # 포트포워딩 API 인증 키
```

### 4️⃣ 인증 및 사용자 관리 🔑

```
POST /api/v1/login                      # 로그인 (JWT 토큰 발급)
POST /api/v1/signup                     # 회원가입
POST /api/v1/logout                     # 로그아웃
GET  /api/v1/profile                    # 프로필 조회
POST /api/v1/switch_project/{id}        # 프로젝트 전환
GET  /api/v1/sso                        # SSO 설정 조회
```

**인증 방식:**
- JWT 토큰 기반 인증
- Keystone 토큰 지원
- 자동 토큰 갱신 (1800초)

### 5️⃣ 모니터링 및 성능 📊

```
GET /api/v1/instances/{id}/performance  # 인스턴스 성능 데이터
GET /api/v1/query                        # Prometheus 쿼리
GET /api/v1/query_range                  # Prometheus 범위 쿼리
```

### 6️⃣ 활동 로깅 📝

```
GET /api/v1/projectlogs  # 프로젝트별 활동 로그 (한국어)
```

**로그 예시:**
```
인스턴스 'my-vm' 생성 완료
볼륨 'my-volume' 연결 완료  
인스턴스 'my-vm' 시작 완료
```

---

## 🏗️ 시스템 아키텍처

### 전체 구조도

```mermaid
graph TB
    subgraph "Client Layer"
        UI[Skyline UI<br/>Next.js Dashboard]
    end
    
    subgraph "API Layer"
        API[Skyline API Server<br/>FastAPI + Gunicorn]
        AUTH[JWT Middleware<br/>Token Validation]
    end
    
    subgraph "Business Logic"
        INST[Instance Handler]
        VOL[Volume Handler]
        PF[PortForward Client]
        LOG[Activity Logger]
    end
    
    subgraph "External Services"
        OS[OpenStack Services<br/>Nova, Cinder, Neutron]
        PROXY[Proxy VM API<br/>Port Forwarding Service]
        PROM[Prometheus<br/>Metrics]
    end
    
    subgraph "Data Layer"
        DB[(Database<br/>SQLite/MySQL)]
    end
    
    UI --> API
    API --> AUTH
    AUTH --> INST
    AUTH --> VOL
    AUTH --> PF
    
    INST --> OS
    VOL --> OS
    PF --> PROXY
    
    INST --> LOG
    VOL --> LOG
    LOG --> DB
    
    API --> PROM
```

### 주요 컴포넌트

| 컴포넌트 | 역할 | 파일 위치 |
|----------|------|-----------|
| **FastAPI App** | 메인 애플리케이션 | `skyline_apiserver/main.py` |
| **API Router** | API 엔드포인트 라우팅 | `skyline_apiserver/api/v1/` |
| **OpenStack Clients** | OpenStack 서비스 통신 | `skyline_apiserver/client/openstack/` |
| **PortForward Client** | 외부 포트포워딩 API 통신 | `skyline_apiserver/client/portforward_client.py` |
| **Database Models** | ORM 모델 및 마이그레이션 | `skyline_apiserver/db/` |
| **Schemas** | Pydantic 스키마 (요청/응답) | `skyline_apiserver/schemas/` |
| **Config** | 설정 관리 | `skyline_apiserver/config/` |

---

## 🚀 빠른 시작

### 사전 요구사항

- Python 3.8 이상
- OpenStack 클라우드 환경 (Keystone, Nova, Cinder, Neutron)
- MySQL 또는 SQLite
- (선택) 외부 포트포워딩 API 서버

### 1. 설치

```bash
# 1. 저장소 클론
git clone https://github.com/your-org/skyline-apiserver-extenstion.git
cd skyline-apiserver-extenstion

# 2. 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 설정 파일 복사
sudo mkdir -p /etc/skyline
sudo cp etc/skyline.yaml.sample /etc/skyline/skyline.yaml
```

### 2. 설정

`/etc/skyline/skyline.yaml` 파일을 환경에 맞게 수정:

```yaml
default:
  database_url: mysql://skyline:password@localhost/skyline
  debug: true
  log_dir: /var/log/skyline
  secret_key: "YOUR-SECRET-KEY-HERE"  # 변경 필수!

openstack:
  keystone_url: http://your-keystone:5000/v3/
  default_region: RegionOne
  
  # 포트포워딩 API 설정 (선택)
  portforward_api_url: http://proxy-vm:8080/api/v1
```

### 3. 데이터베이스 마이그레이션

```bash
# Alembic을 사용한 DB 스키마 생성
make db_sync
```

### 4. 실행

#### 개발 모드 (Swagger UI 활성화)

```bash
uvicorn --reload --reload-dir skyline_apiserver --port 28000 --log-level debug skyline_apiserver.main:app
```

#### 프로덕션 모드

```bash
# Swagger UI 비활성화
SKYLINE_ENV=production gunicorn -c /etc/skyline/gunicorn.py skyline_apiserver.main:app
```

### 5. 접속

- **Swagger UI**: http://localhost:28000/docs
- **API Base URL**: http://localhost:28000/api/v1/

---

## ⚙️ 설정 가이드

### 설정 파일 구조

`/etc/skyline/skyline.yaml`는 세 가지 주요 섹션으로 구성됩니다:

#### 1. `default` - 일반 설정

```yaml
default:
  # 데이터베이스
  database_url: mysql://user:pass@localhost/skyline
  
  # 로깅
  log_dir: /var/log/skyline
  log_file: skyline.log
  debug: false
  
  # JWT 토큰
  secret_key: "CHANGE-ME"           # 반드시 변경!
  access_token_expire: 3600         # 1시간
  access_token_renew: 1800          # 30분 후 자동 갱신
  
  # CORS
  cors_allow_origins:
    - http://localhost:3000
    - https://your-dashboard.com
  
  # Prometheus
  prometheus_endpoint: http://localhost:9091
  prometheus_enable_basic_auth: false
```

#### 2. `openstack` - OpenStack 설정

```yaml
openstack:
  # Keystone
  keystone_url: http://controller:5000/v3/
  default_region: RegionOne
  interface_type: public
  
  # 시스템 사용자 (관리 작업용)
  system_user_name: skyline
  system_user_password: "skyline-password"
  system_user_domain: Default
  system_project: service
  system_project_domain: Default
  
  # 역할
  system_admin_roles:
    - admin
    - system_admin
  
  # 포트포워딩 (확장 기능)
  portforward_api_url: http://proxy-vm:8080/api/v1
  portforward_authorization_key: "your-secret-key-here"  # 외부 API 인증 키
  
  # 할당량 기본값
  nova_quota_instances: 10
  nova_quota_cores: 4
  nova_quota_ram: 6144
  cinder_quota_gigabytes: 100
```

#### 3. `setting` - 플랫폼별 설정

```yaml
setting:
  base_settings:
    - flavor_families
    - gpu_models
  
  flavor_families:
    - architecture: x86_architecture
      categories:
        - name: general_purpose
          properties: []
```

### 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SKYLINE_ENV` | 환경 모드 (`production`이면 Swagger 비활성화) | `development` |

---

## 📚 API 문서

### 인증 헤더

모든 API 요청에는 다음 중 하나의 헤더가 필요합니다:

```http
Authorization: Bearer <jwt-token>
```

또는

```http
X-Auth-Token: <keystone-token>
```

### 주요 API 엔드포인트

상세한 API 문서는 [API.md](./API.md)를 참조하세요.

#### 빠른 참조

```bash
# 로그인
curl -X POST http://localhost:28000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{
    "region": "RegionOne",
    "domain": "Default",
    "username": "user",
    "password": "password"
  }'

# 인스턴스 생성 (SSH 포트포워딩 자동 설정)
curl -X POST http://localhost:28000/api/v1/instances \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-instance",
    "image_id": "image-uuid",
    "flavor_id": "flavor-uuid",
    "network_id": "network-uuid",
    "key_name": "my-keypair",
    "volume_size": 25
  }'

# 포트포워딩 생성
curl -X POST http://localhost:28000/api/v1/portforward \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "web-service",
    "user_vm_id": "instance-uuid",
    "user_vm_name": "my-instance",
    "user_vm_internal_ip": "10.0.0.10",
    "user_vm_internal_port": 80,
    "service_type": "other",
    "protocol": "tcp"
  }'
```

### Swagger UI

개발 모드에서는 자동 생성된 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:28000/docs
- **ReDoc**: http://localhost:28000/redoc

---

## 📁 프로젝트 구조

```
skyline-apiserver-extenstion/
├── skyline_apiserver/              # 메인 애플리케이션
│   ├── main.py                     # FastAPI 앱 (엔트리포인트)
│   ├── __main__.py                 # CLI 실행
│   ├── context.py                  # 요청 컨텍스트
│   │
│   ├── api/                        # API 라우터
│   │   ├── deps.py                 # 의존성 주입
│   │   └── v1/                     # v1 API
│   │       ├── __init__.py         # API 라우터 등록
│   │       ├── login.py            # 인증 (로그인/회원가입/SSO)
│   │       ├── instance.py         # 인스턴스 관리 (생성/삭제/시작/정지)
│   │       ├── portforward.py      # 포트포워딩 (Proxy API 연동)
│   │       ├── extension.py        # 확장 API (서버/볼륨 목록)
│   │       ├── flavor.py           # Flavor 관리
│   │       ├── image.py            # 이미지 조회
│   │       ├── network.py          # 네트워크 조회
│   │       ├── keypair.py          # 키페어 관리
│   │       ├── limits.py           # 할당량 조회
│   │       ├── performance.py      # 성능 모니터링
│   │       ├── prometheus.py       # Prometheus 쿼리
│   │       └── logs.py             # 활동 로그
│   │
│   ├── client/                     # 외부 서비스 클라이언트
│   │   ├── openstack/              # OpenStack 클라이언트
│   │   │   ├── nova.py             # Nova (인스턴스)
│   │   │   ├── cinder.py           # Cinder (볼륨)
│   │   │   ├── neutron.py          # Neutron (네트워크)
│   │   │   └── keystone.py         # Keystone (인증)
│   │   ├── portforward_client.py   # 외부 포트포워딩 API 클라이언트
│   │   └── utils.py                # 클라이언트 유틸리티
│   │
│   ├── config/                     # 설정
│   │   └── __init__.py             # 설정 로더
│   │
│   ├── core/                       # 핵심 로직
│   │   └── security.py             # JWT, 인증
│   │
│   ├── db/                         # 데이터베이스
│   │   ├── api.py                  # DB API
│   │   ├── models.py               # SQLAlchemy 모델
│   │   └── alembic/                # 마이그레이션
│   │
│   ├── schemas/                    # Pydantic 스키마
│   │   ├── login.py                # 로그인 요청/응답
│   │   ├── instance.py             # 인스턴스 요청/응답
│   │   ├── portforward.py          # 포트포워딩 요청/응답
│   │   └── ...
│   │
│   ├── policy/                     # 권한 정책
│   ├── log/                        # 로깅
│   ├── utils/                      # 유틸리티
│   └── types/                      # 타입 정의
│
├── etc/                            # 설정 파일
│   ├── skyline.yaml.sample         # 설정 샘플
│   └── gunicorn.py                 # Gunicorn 설정
│
├── container/                      # Docker 이미지
├── spec/                           # 설계 문서
├── tools/                          # 유틸리티 스크립트
│
├── requirements.txt                # Python 의존성
├── setup.py                        # 패키지 설정
├── setup.cfg                       # 패키지 메타데이터
├── Makefile                        # 빌드/개발 명령어
├── API.md                          # API 레퍼런스
└── README.md                       # 이 문서
```

### 핵심 모듈 설명

#### 1. API Layer (`api/v1/`)

각 파일은 하나의 리소스를 담당합니다:

- **login.py**: 인증 (로그인, 회원가입, 토큰 관리)
- **instance.py**: 인스턴스 CRUD + 시작/정지/재시작
- **portforward.py**: 외부 API와의 포트포워딩 연동
- **extension.py**: 서버/볼륨 목록 등 확장 기능

#### 2. Client Layer (`client/`)

외부 서비스와의 통신을 담당:

- **openstack/**: OpenStack Python 클라이언트 래퍼
- **portforward_client.py**: **중요!** 외부 포트포워딩 API와 HTTP 통신

#### 3. Database Layer (`db/`)

- **models.py**: SQLAlchemy ORM 모델
- **alembic/**: 데이터베이스 스키마 마이그레이션

#### 4. Schemas (`schemas/`)

Pydantic 모델로 요청/응답 검증:

```python
# schemas/instance.py 예시
class InstanceCreate(BaseModel):
    name: str
    image_id: str
    flavor_id: str
    network_id: str
    key_name: Optional[str] = None
    volume_size: int = 20
```

---

## 🔧 개발 가이드

### 개발 환경 설정

```bash
# 1. 개발 의존성 설치
pip install -r requirements.txt
pip install -r test-requirements.txt

# 2. pre-commit 설정 (코드 품질)
pip install pre-commit
pre-commit install

# 3. 개발 서버 실행 (자동 리로드)
make run

# 또는
uvicorn --reload --reload-dir skyline_apiserver --port 28000 skyline_apiserver.main:app
```

### Makefile 명령어

```bash
make db_sync      # 데이터베이스 마이그레이션
make run          # 개발 서버 실행
make test         # 테스트 실행
make lint         # 코드 린트 (flake8, mypy)
make format       # 코드 포맷팅 (black, isort)
```

### 새 API 엔드포인트 추가하기

1. **스키마 정의** (`schemas/your_resource.py`):

```python
from pydantic import BaseModel

class YourResourceCreate(BaseModel):
    name: str
    description: str
```

2. **API 라우터 생성** (`api/v1/your_resource.py`):

```python
from fastapi import APIRouter, Depends
from skyline_apiserver.schemas.your_resource import YourResourceCreate

router = APIRouter()

@router.post("")
async def create_resource(
    payload: YourResourceCreate,
    # context: RequestContext = Depends(deps.get_context),
):
    # 비즈니스 로직
    return {"id": "new-id", "name": payload.name}
```

3. **라우터 등록** (`api/v1/__init__.py`):

```python
from skyline_apiserver.api.v1 import your_resource

api_router.include_router(
    your_resource.router,
    prefix="/your-resources",
    tags=["YourResource"],
)
```

### 데이터베이스 마이그레이션

```bash
# 새 마이그레이션 생성
alembic revision --autogenerate -m "Add new table"

# 마이그레이션 적용
alembic upgrade head

# 롤백
alembic downgrade -1
```

### 테스트 작성

```python
# skyline_apiserver/tests/test_instance.py
from fastapi.testclient import TestClient
from skyline_apiserver.main import app

client = TestClient(app)

def test_create_instance():
    response = client.post("/api/v1/instances", json={
        "name": "test-instance",
        "image_id": "test-image",
        "flavor_id": "test-flavor",
    })
    assert response.status_code == 202
```

---

## 🔍 트러블슈팅

### 1. 데이터베이스 연결 실패

**증상:**
```
sqlalchemy.exc.OperationalError: (MySQLdb._exceptions.OperationalError) (2003, "Can't connect to MySQL server")
```

**해결:**
- `skyline.yaml`의 `database_url` 확인
- 데이터베이스 서버 실행 상태 확인
- 방화벽 설정 확인

### 2. OpenStack 인증 실패

**증상:**
```
keystoneauth1.exceptions.http.Unauthorized: The request you have made requires authentication. (HTTP 401)
```

**해결:**
- `keystone_url` 확인
- `system_user_name`과 `system_user_password` 확인
- OpenStack RC 파일로 수동 인증 테스트

### 3. 포트포워딩 API 연결 실패

**증상:**
```
PortForwardClientError: PortForward API Error (500): Connection refused
```

**해결:**
- `portforward_api_url` 확인
- 외부 Proxy VM API 서버 실행 상태 확인
- 네트워크 연결 확인 (`curl http://proxy-vm:8080/health`)

### 4. Swagger UI가 표시되지 않음

**증상:** `/docs`에 접속해도 404 오류

**해결:**
```bash
# 환경 변수 확인 (production이면 Swagger 비활성화됨)
echo $SKYLINE_ENV

# development 모드로 실행
unset SKYLINE_ENV
uvicorn skyline_apiserver.main:app --reload
```

### 5. JWT 토큰 만료

**증상:**
```
{"detail": "Could not validate credentials"}
```

**해결:**
- 로그인 API로 새 토큰 발급
- `access_token_expire` 설정 조정 (기본 3600초)

### 로그 확인

```bash
# 애플리케이션 로그
tail -f /var/log/skyline/skyline.log

# 개발 모드에서는 콘솔 출력 확인
DEBUG:skyline_apiserver:Request path: /api/v1/instances
```

---

## 📝 변경 이력

### 2026-02-10: Floating IP 설정 필드 제거

포트포워딩이 외부 API (`portforward_api_url`)를 통해 할당되도록 변경됨에 따라, 아래 설정 필드와 관련 코드가 **삭제**되었습니다:

| 삭제된 설정 | 설명 |
|-------------|------|
| `shared_floating_ip_project_id` | 공유 Floating IP 프로젝트 ID |
| `portforward_floating_ip_ids` | 포트포워딩용 Floating IP 목록 |
| `ssh_floating_ip_id` | SSH 포트포워딩용 Floating IP ID |

**삭제된 함수 (`neutron.py`):**
- `find_floating_ip_for_ssh()` — SSH Floating IP 조회
- `find_available_floating_ip()` — 공유 프로젝트에서 Floating IP 조회
- `find_portforward_floating_ip()` — 랜덤 Floating IP 선택

**변경된 동작:**
- `POST /api/v1/port_forwardings` — `floating_ip` 파라미터가 **필수**로 변경 (자동 선택 제거)
- `GET /api/v1/port_forwardings/stats` — 설정 목록 대신 모든 Floating IP에서 포트포워딩 조회

> ⚠️ `skyline.yaml`에서 위 3개 설정을 사용 중이라면 제거해주세요. 남아 있어도 무시되지만 혼란을 방지하기 위해 삭제를 권장합니다.

---

## 📄 라이선스

Apache License 2.0 - 자세한 내용은 [LICENSE](./LICENSE) 파일을 참조하세요.

---

## 🤝 기여

이 프로젝트는 DCloud 플랫폼을 위한 내부 프로젝트이지만, 개선 사항이나 버그 리포트는 언제나 환영합니다!

---

## 📞 지원

- **API 문서**: [API.md](./API.md)
- **설계 문서**: [spec/](./spec/)
- **OpenStack Skyline 공식 문서**: https://docs.openstack.org/skyline-apiserver/

---

**Made with ❤️ for DCloud Platform**
