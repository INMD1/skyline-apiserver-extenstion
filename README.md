# 경고!
> 본 APi서버는 Skyline에서 추가적으로 기능이 추가된 버전입니다. <br/>
> 아직 개발 중이여서 버그가 발생 할수 있습니다.
> 
# Skyline

Skyline은 OpenStack 대시보드로, UI/UX가 최적화되어 있으며 OpenStack **Train** 버전 이상을 지원합니다.
현대적인 기술 스택과 생태계를 갖추고 있어 개발자가 더 쉽게 유지관리할 수 있고, 사용자 입장에서도 더 뛰어난 성능과 높은 동시성 처리 능력을 제공합니다.

Skyline의 마스코트는 **구색 사슴(아홉 가지 색의 사슴)** 입니다.
이 사슴은 둔황 벽화 "구색왕록"에서 유래한 것으로, 인과응보와 감사의 의미를 지니고 있으며, 이는 Skyline의 주체인 99cloud가 커뮤니티를 포용하고 환원해 온 철학과도 맞닿아 있습니다.
Skyline 또한 이 구색 사슴처럼 가볍고, 우아하며, 강력한 오픈스택 대시보드가 되기를 바랍니다.


##  목차

* [Skyline API Server](#skyline-api-server)

  * [리소스](#resources)
  * [빠른 시작](#quick-start)

    * [사전 준비 사항](#prerequisites)
    * [설정](#configure)
    * [Sqlite를 이용한 배포](#deployment-with-sqlite)
    * [MariaDB를 이용한 배포](#deployment-with-mariadb)
    * [접속 테스트](#test-access)
  * [Skyline API 서버 개발](#develop-skyline-apiserver)

    * [필수 도구](#dependent-tools)
    * [설치 및 실행](#install--run)

##  빠른 시작

###  사전 준비 사항

* Keystone 엔드포인트를 통해 OpenStack 구성 요소에 접근 가능한 환경
* 컨테이너 엔진이 설치된 리눅스 서버 (예: [Docker](https://docs.docker.com/engine/install/) 또는 [Podman](https://podman.io/getting-started/installation))


### ⚙️ 설정

1. 리눅스 서버의 `/etc/skyline/skyline.yaml` 파일 수정
   [샘플 파일](etc/skyline.yaml.sample)을 참고하여 아래의 항목을 실제 환경에 맞게 설정:

   ```
   database_url
   keystone_url
   default_region
   interface_type
   system_project_domain
   system_project
   system_user_domain
   system_user_name
   system_user_password
   ```

2. Prometheus 연동 시 아래 항목도 설정:

   ```
   prometheus_basic_auth_password
   prometheus_basic_auth_user
   prometheus_enable_basic_auth
   prometheus_endpoint
   ```


### Sqlite를 이용한 배포

1. 부트스트랩 컨테이너 실행:

```bash
rm -rf /tmp/skyline && mkdir /tmp/skyline && mkdir /var/log/skyline

docker run -d --name skyline_bootstrap \
  -e KOLLA_BOOTSTRAP="" \
  -v /var/log/skyline:/var/log/skyline \
  -v /etc/skyline/skyline.yaml:/etc/skyline/skyline.yaml \
  -v /tmp/skyline:/tmp --net=host 99cloud/skyline:latest

# 정상적으로 부트스트랩되었는지 확인
docker logs skyline_bootstrap
```

2. 부트스트랩 완료 후 Skyline 서비스 실행:

```bash
docker rm -f skyline_bootstrap

docker run -d --name skyline --restart=always \
  -v /var/log/skyline:/var/log/skyline \
  -v /etc/skyline/skyline.yaml:/etc/skyline/skyline.yaml \
  -v /tmp/skyline:/tmp --net=host 99cloud/skyline:latest
```

※ 포트를 변경하려면 `-e LISTEN_ADDRESS=<ip:port>` 추가
※ 정책 파일 경로는 `/etc/skyline/policy/<서비스명>_policy.yaml`

---

### MariaDB를 이용한 배포

공식 문서 참고:
[https://docs.openstack.org/skyline-apiserver/latest/install/docker-install-ubuntu.html](https://docs.openstack.org/skyline-apiserver/latest/install/docker-install-ubuntu.html)

---

### API 문서 접속

브라우저에서 접속:
`https://<ip_address>:9999/api/openstack/skyline/docs`

---

### 접속 테스트

브라우저에서 대시보드 확인:
`https://<ip_address>:9999`

---

## Skyline API 서버 개발

**Linux 또는 MacOS 지원 (Linux 권장)**
※ Python 3.8 이상 필요, uvloop 사용

### 필수 도구

* make ≥ 3.82
* python ≥ 3.9
* node ≥ 10.22.0 (옵션, 콘솔 개발 시만 필요)
* yarn ≥ 1.22.4 (옵션)

### 설치 및 실행

1. 의존성 설치

```bash
tox -e venv
. .tox/venv/bin/activate
pip install -r requirements.txt -r test-requirements.txt -c https://releases.openstack.org/constraints/upper/master
pip install -e .
```

2. 설정 파일 복사 및 편집

```bash
cp etc/skyline.yaml.sample etc/skyline.yaml
export OS_CONFIG_DIR=$(pwd)/etc
```

3. DB 초기화

```bash
source .tox/venv/bin/activate
make db_sync
deactivate
```

4. API 서버 실행

```bash
source .tox/venv/bin/activate
uvicorn --reload --reload-dir skyline_apiserver --port 28000 --log-level debug skyline_apiserver.main:app
```

* 접속: `http://127.0.0.1:28000/docs`
* VSCode 디버깅도 가능

5. 도커 이미지 빌드

```bash
make build
```

---

## FAQ

### Q1. 일반 사용자로 로그인은 되지만, Nova 서버 목록 조회는 왜 안 되나요?

**증상*

* Horizon: 일반 사용자 A → 서버 목록 조회 가능
* Skyline: 동일 사용자 A → 401 오류 (서버 목록 안 보임), F12에서 HTTP 요청 없음

**원인 분석**

* Horizon은 권한 체크 없이 요청 전달 → 서비스(Nova)에서 정책 확인
* Skyline은 자체적으로 `/policy` API로 사전 체크
  → 정책 파일이 제대로 설정되지 않으면 401

**해결 방법**

* 기본적으로 `project_reader_api`: `"role:reader and project_id:%(project_id)s"` 필요
* 커스텀 역할(member, *member*, projectAdmin 등)을 reader 역할에 암시적으로 매핑해야 함:

```bash
openstack implied role create --implied-role reader _member_
openstack implied role create --implied-role member projectAdmin
```

**확인 명령어**

```bash
openstack implied role list
```

---
