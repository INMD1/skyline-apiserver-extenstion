# Skyline API Server Extension

> ⚠️ **경고:** 본 API 서버는 Skyline에서 기능이 확장된 버전입니다. 아직 개발 중이므로 버그가 발생할 수 있습니다.

## 소개

**Skyline**은 OpenStack 대시보드로, 현대적인 UI/UX와 높은 동시성 처리 능력을 제공합니다. 본 프로젝트는 Skyline의 확장 버전으로, DCloud 플랫폼을 위한 추가 기능을 제공합니다.

## 주요 기능

- 🖥️ **인스턴스 관리**: 생성, 삭제, 시작, 정지, 재시작, 콘솔 접속
- 📦 **볼륨 관리**: 생성, 삭제, 연결, 분리
- 🔌 **포트포워딩**: 외부 Proxy VM API 연동, SSH 자동 포트포워딩
- 🔑 **인증**: 로그인, 회원가입, SSO, 프로젝트 전환
- 📊 **모니터링**: Prometheus 쿼리, 성능 데이터 조회
- 📝 **활동 로깅**: 모든 작업을 한국어로 기록

## 기술 스택

| 분류 | 기술 |
|------|------|
| Web Framework | FastAPI |
| ASGI Server | Uvicorn, Gunicorn |
| Database ORM | SQLAlchemy |
| Database Migration | Alembic |
| OpenStack Clients | keystoneclient, novaclient, neutronclient 등 |

## 설치

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 설정 파일 복사
cp etc/skyline.yaml.sample /etc/skyline/skyline.yaml

# 3. 데이터베이스 마이그레이션
make db_sync
```

## 설정

`/etc/skyline/skyline.yaml` 파일에서 다음 항목을 환경에 맞게 수정합니다:

```yaml
default:
  database_url: mysql://user:pass@localhost/skyline

openstack:
  keystone_url: http://keystone:5000/v3
  portforward_api_url: http://proxy-vm:8080/api/v1  # 포트포워딩 API
```

## 실행

### 개발 환경
```bash
uvicorn --reload --reload-dir skyline_apiserver --port 28000 --log-level debug skyline_apiserver.main:app
```

### 프로덕션 환경
```bash
# Swagger 문서 비활성화
SKYLINE_ENV=production gunicorn -c /etc/skyline/gunicorn.py skyline_apiserver.main:app
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SKYLINE_ENV` | 환경 설정 (`production`이면 Swagger 비활성화) | `development` |

## API 문서

- **개발 환경**: `http://localhost:28000/docs` (Swagger UI)
- **상세 API 문서**: [API.md](./API.md)

## 프로젝트 구조

```
skyline_apiserver/
├── api/v1/           # API 라우터
│   ├── login.py      # 인증 (로그인/로그아웃/회원가입)
│   ├── instance.py   # 인스턴스 관리
│   ├── portforward.py # 포트포워딩 (Proxy VM 연동)
│   ├── extension.py  # 확장 API (서버/볼륨 목록)
│   └── ...
├── client/           # OpenStack 클라이언트
│   ├── openstack/    # Nova, Neutron, Cinder 등
│   └── portforward_client.py # 외부 포트포워딩 API 클라이언트
├── config/           # 설정
├── db/               # 데이터베이스
└── schemas/          # Pydantic 스키마
```

## 라이선스

Apache License 2.0
