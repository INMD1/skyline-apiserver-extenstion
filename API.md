# Skyline API Server Extension - API Reference

## 인증

모든 API 요청에는 헤더가 필요합니다:
```
Authorization: Bearer <jwt-token>
```
또는
```
X-Auth-Token: <keystone-token>
```

---

## 인증 API

### 로그인
```http
POST /api/v1/login
```

**Request:**
```json
{
  "region": "RegionOne",
  "domain": "Default",
  "username": "user",
  "password": "password"
}
```

### 회원가입
```http
POST /api/v1/signup
```

### 프로필 조회
```http
GET /api/v1/profile
```

### 로그아웃
```http
POST /api/v1/logout
```

### 프로젝트 전환
```http
POST /api/v1/switch_project/{project_id}
```

### SSO 설정 조회
```http
GET /api/v1/sso
```

---

## 인스턴스 API

### 인스턴스 생성
```http
POST /api/v1/instances
```

**Request:**
```json
{
  "name": "my-instance",
  "image_id": "image-uuid",
  "flavor_id": "flavor-uuid",
  "key_name": "my-keypair",
  "network_id": "network-uuid",
  "volume_size": 25,
  "additional_ports": [
    {"internal_port": 80, "external_port": 8080, "protocol": "tcp"}
  ]
}
```

**Response:** `202 Accepted`
```json
{
  "request_id": "uuid",
  "status": "PENDING"
}
```

> 인스턴스 생성 시 SSH 포트포워딩(포트 22)이 자동으로 설정됩니다.

### 인스턴스 조회
```http
GET /api/v1/instances/{instance_id}
```

### 인스턴스 삭제
```http
DELETE /api/v1/instances/{instance_id}
```
> 연결된 볼륨과 포트포워딩 규칙도 함께 삭제됩니다.

### 인스턴스 시작
```http
POST /api/v1/instances/{instance_id}/start
```

### 인스턴스 정지
```http
POST /api/v1/instances/{instance_id}/stop
```

### 인스턴스 재시작
```http
POST /api/v1/instances/{instance_id}/reboot
```

**Request (선택):**
```json
{
  "reboot_type": "SOFT"  // SOFT (기본값) 또는 HARD
}
```

### 콘솔 URL 조회
```http
POST /api/v1/instances/{instance_id}/console
```

**Request:**
```json
{
  "console_type": "novnc"
}
```

---

## 볼륨 API

### 볼륨 목록 조회
```http
GET /api/v1/extension/volumes
```

### 볼륨 삭제
```http
DELETE /api/v1/volumes/{volume_id}
```

### 볼륨 연결
```http
POST /api/v1/instances/{instance_id}/volumes/attach
```

**Request:**
```json
{
  "volume_id": "volume-uuid"
}
```

### 볼륨 분리
```http
POST /api/v1/instances/{instance_id}/volumes/detach
```

---

## 포트포워딩 API

> 외부 Proxy VM API와 연동됩니다.

### 포트포워딩 생성
```http
POST /api/v1/portforward
```

**Request:**
```json
{
  "rule_name": "my-service",
  "user_vm_id": "instance-uuid",
  "user_vm_name": "my-instance",
  "user_vm_internal_ip": "10.0.0.10",
  "user_vm_internal_port": 80,
  "service_type": "other",  // "ssh" 또는 "other"
  "protocol": "tcp"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "rule_id": "uuid",
  "proxy_external_ip": "203.0.113.10",
  "proxy_external_port": 20001,
  ...
}
```

### 포트포워딩 목록 조회
```http
GET /api/v1/portforward
```

**Query Parameters:**
- `status_filter`: 상태 필터
- `floating_ip`: Floating IP 필터
- `service_type`: 서비스 유형 (ssh/other)
- `vm_id`: VM ID 필터

### VM별 포트포워딩 조회
```http
GET /api/v1/portforward/vm/{vm_id}
```

### 포트포워딩 상세 조회
```http
GET /api/v1/portforward/{rule_id}
```

### 포트포워딩 수정
```http
PATCH /api/v1/portforward/{rule_id}
```

### 포트포워딩 삭제
```http
DELETE /api/v1/portforward/{rule_id}
```

### 시스템 상태 조회
```http
GET /api/v1/portforward/status
```

### Floating IP 상태 조회
```http
GET /api/v1/portforward/floating-ips
```

### 포트 할당 미리보기
```http
GET /api/v1/portforward/port-allocation/preview?service_type=ssh
```

---

## 리소스 조회 API

### 서버 목록
```http
GET /api/v1/extension/servers
```

### 이미지 목록
```http
GET /api/v1/images
```

### Flavor 목록
```http
GET /api/v1/flavors
```

### Flavor 상세
```http
GET /api/v1/flavors/{flavor_id}
```

### 네트워크 목록
```http
GET /api/v1/networks
```

### 키페어 목록
```http
GET /api/v1/keypairs
```

### 키페어 생성
```http
POST /api/v1/keypairs
```

**Request:**
```json
{
  "name": "my-keypair",
  "public_key": "ssh-rsa AAAA..."  // 선택
}
```

### 키페어 삭제
```http
DELETE /api/v1/keypairs/{keypair_name}
```

---

## 리소스 제한 API

### 리소스 사용량 조회
```http
GET /api/v1/limits
```

---

## 성능 모니터링 API

### 인스턴스 성능 데이터
```http
GET /api/v1/instances/{instance_id}/performance
```

### Prometheus 쿼리
```http
GET /api/v1/query?query={promql}
```

### Prometheus 범위 쿼리
```http
GET /api/v1/query_range?query={promql}&start={timestamp}&end={timestamp}&step={step}
```

---

## 활동 로그 API

### 프로젝트 활동 로그 조회
```http
GET /api/v1/projectlogs
```

---

## 오류 응답

모든 API는 다음 형식으로 오류를 반환합니다:

```json
{
  "detail": "오류 메시지"
}
```

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 |
| 403 | 권한 없음 |
| 404 | 리소스를 찾을 수 없음 |
| 500 | 서버 오류 |
