# Skyline API Server Extension - API Documentation

본 문서는 Skyline API Server에 추가된 포트포워딩 및 볼륨(디스크) 관리 API들에 대한 상세 가이드입니다.

## 목차
1. [포트포워딩 API](#포트포워딩-api)
2. [볼륨 관리 API](#볼륨-관리-api)
3. [VM 인스턴스 API 확장](#vm-인스턴스-api-확장)
4. [설정 가이드](#설정-가이드)

---

## 포트포워딩 API

### 1. 포트포워딩 생성

**Endpoint**: `POST /api/v1/port_forwardings`

VM에 새로운 포트포워딩 규칙을 추가합니다. 시스템은 자동으로 해당 VM에 최적의 Floating IP를 할당합니다.

**특징**:
- **Sticky IP 할당**: VM이 이미 포트포워딩을 가지고 있으면 동일한 IP 사용
- **자동 포트 선택**: `external_port`를 null로 설정하면 자동으로 사용 가능한 포트 할당
- **쿼터 확인**: 프로젝트의 포트포워딩 한도 초과 여부 자동 확인

**Request Body**:
```json
{
  "internal_ip": "10.0.0.5",
  "internal_port": 8080,
  "external_port": 30080,
  "protocol": "tcp"
}
```

**Parameters**:
- `internal_ip` (required): VM의 내부 IP 주소
- `internal_port` (required): VM의 내부 포트
- `external_port` (optional): 외부 포트. `null`이면 자동 할당
- `protocol` (optional): 프로토콜 (기본값: "tcp")

**Response** (200 OK):
```json
{
  "message": "Port forwarding created successfully",
  "port_forwarding": {
    "id": "pf-uuid",
    "protocol": "tcp",
    "internal_ip_address": "10.0.0.5",
    "internal_port": 8080,
    "external_port": 30080
  }
}
```

**Example (자동 포트 할당)**:
```bash
curl -X POST http://localhost:28000/api/v1/port_forwardings \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-token" \
  -d '{
    "internal_ip": "10.0.0.5",
    "internal_port": 3000,
    "external_port": null,
    "protocol": "tcp"
  }'
```

---

### 2. 포트포워딩 삭제

**Endpoint**: `DELETE /api/v1/port_forwardings`

기존 포트포워딩 규칙을 제거합니다.

**Request Body**:
```json
{
  "floating_ip_id": "fip-uuid",
  "pf_id": "pf-uuid"
}
```

**Response**: `204 No Content`

**Example**:
```bash
curl -X DELETE http://localhost:28000/api/v1/port_forwardings \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-token" \
  -d '{
    "floating_ip_id": "abc-123",
    "pf_id": "pf-456"
  }'
```

---

## 볼륨 관리 API

### 1. 볼륨 생성

**Endpoint**: `POST /api/v1/volumes`

새 볼륨을 생성합니다 (부팅 가능 또는 데이터 볼륨).

**Request Body**:
```json
{
  "name": "my-volume",
  "size": 10,
  "description": "Data volume for project",
  "image_id": null
}
```

**Parameters**:
- `name` (required): 볼륨 이름
- `size` (required): 볼륨 크기 (GB)
- `description` (optional): 볼륨 설명
- `image_id` (optional): 부팅 가능 볼륨을 만들려면 이미지 ID 지정

**Response** (201 Created):
```json
{
  "id": "vol-uuid",
  "name": "my-volume",
  "size": 10,
  "status": "creating",
  "created_at": "2026-01-16T12:00:00Z"
}
```

**Example**:
```bash
curl -X POST http://localhost:28000/api/v1/volumes \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-token" \
  -d '{
    "name": "data-volume",
    "size": 20
  }'
```

---

### 2. 볼륨 삭제

**Endpoint**: `DELETE /api/v1/volumes/{volume_id}`

볼륨을 삭제합니다. 볼륨이 VM에 연결되어 있으면 실패합니다.

**Response**: `204 No Content`

**Error** (400 Bad Request):
```json
{
  "detail": "Cannot delete volume that is attached to an instance. Detach it first."
}
```

**Example**:
```bash
curl -X DELETE http://localhost:28000/api/v1/volumes/vol-uuid \
  -H "X-Auth-Token: your-token"
```

---

### 3. 볼륨 연결

**Endpoint**: `POST /api/v1/instances/{instance_id}/volumes`

볼륨을 VM 인스턴스에 연결합니다.

**Request Body**:
```json
{
  "volume_id": "vol-uuid"
}
```

**Response** (200 OK):
```json
{
  "message": "Volume attached successfully",
  "attachment": {
    "id": "attach-uuid",
    "volumeId": "vol-uuid",
    "serverId": "instance-uuid",
    "device": "/dev/vdb"
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:28000/api/v1/instances/vm-123/volumes \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-token" \
  -d '{
    "volume_id": "vol-456"
  }'
```

---

### 4. 볼륨 해제

**Endpoint**: `DELETE /api/v1/instances/{instance_id}/volumes/{volume_id}`

VM 인스턴스에서 볼륨을 분리합니다.

**Response**: `204 No Content`

**Example**:
```bash
curl -X DELETE http://localhost:28000/api/v1/instances/vm-123/volumes/vol-456 \
  -H "X-Auth-Token: your-token"
```

---

## VM 인스턴스 API 확장

### VM 조회 (포트포워딩 정보 포함)

**Endpoint**: `GET /api/v1/instances/{instance_id}`

VM 정보를 조회하며, VM에 연결된 모든 포트포워딩 규칙을 포함합니다.

**Response** (200 OK):
```json
{
  "id": "vm-uuid",
  "name": "my-instance",
  "status": "ACTIVE",
  "created": "2026-01-15T10:00:00Z",
  "updated": "2026-01-16T11:00:00Z",
  "flavor": {
    "id": "flavor-uuid",
    "name": "m1.small"
  },
  "image": {
    "id": "image-uuid"
  },
  "addresses": {
    "private": [
      {
        "addr": "10.0.0.5",
        "OS-EXT-IPS:type": "fixed"
      }
    ]
  },
  "port_forwardings": [
    {
      "id": "pf-1",
      "floating_ip_id": "fip-uuid",
      "floating_ip_address": "203.0.113.10",
      "internal_ip_address": "10.0.0.5",
      "internal_port": 22,
      "external_port": 12345,
      "protocol": "tcp"
    },
    {
      "id": "pf-2",
      "floating_ip_id": "fip-uuid",
      "floating_ip_address": "203.0.113.10",
      "internal_ip_address": "10.0.0.5",
      "internal_port": 80,
      "external_port": 30080,
      "protocol": "tcp"
    }
  ]
}
```

**Example**:
```bash
curl -X GET http://localhost:28000/api/v1/instances/vm-uuid \
  -H "X-Auth-Token: your-token"
```

---

### VM 생성 (포트포워딩 자동 설정)

**Endpoint**: `POST /api/v1/instances`

VM을 생성하면 자동으로 SSH 포트포워딩이 설정됩니다.

**Request Body**:
```json
{
  "name": "my-vm",
  "image_id": "image-uuid",
  "flavor_id": "flavor-uuid",
  "key_name": "my-keypair",
  "network_id": "network-uuid",
  "volume_size": null,
  "additional_ports": [
    {
      "internal_port": 80,
      "external_port": 8080,
      "protocol": "tcp"
    }
  ]
}
```

**특징**:
- SSH 포트(22)는 자동으로 랜덤 포트에 매핑
- `additional_ports`에 추가 포트 지정 가능
- `external_port`를 생략하면 자동 할당

**Response** (202 Accepted):
```json
{
  "request_id": "req-uuid",
  "status": "PENDING"
}
```

---

## 설정 가이드

### Configuration File

`/etc/skyline/skyline.yaml`에서 포트포워딩 관련 설정을 구성합니다:

```yaml
openstack:
  # SSH 전용 Floating IP ID
  ssh_floating_ip_id: 'ssh-fip-uuid'
  
  # 일반 포트포워딩용 Floating IP ID 배열
  port_forwarding_ip_ids:
    - 'fip-uuid-1'
    - 'fip-uuid-2'
    - 'fip-uuid-3'
  
  # 프로젝트당 최대 포트포워딩 개수
  port_forwarding_limit: 10
  
  # 공유 Floating IP 프로젝트 ID (deprecated, port_forwarding_ip_ids 사용 권장)
  shared_floating_ip_project_id: ''
```

### 주요 설정 설명

1. **ssh_floating_ip_id**: SSH 접속 전용으로 사용할 Floating IP의 ID
   - VM 생성 시 자동으로 SSH 포트(22)가 이 IP에 매핑됩니다

2. **port_forwarding_ip_ids**: 일반 포트포워딩에 사용할 Floating IP ID 배열
   - 시스템이 자동으로 부하가 적은 IP를 선택
   - VM이 이미 규칙을 가지고 있으면 같은 IP 우선 사용 (sticky allocation)

3. **port_forwarding_limit**: 프로젝트당 최대 포트포워딩 개수
   - 이 한도를 초과하면 새 포트포워딩 생성 실패

---

## 사용 시나리오

### 시나리오 1: 웹 서버 VM 생성 및 포트 개방

```bash
# 1. VM 생성 (SSH는 자동 설정됨)
curl -X POST http://localhost:28000/api/v1/instances \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: token" \
  -d '{
    "name": "web-server",
    "image_id": "ubuntu-20.04",
    "flavor_id": "m1.small",
    "key_name": "my-key",
    "network_id": "private-net"
  }'

# 2. HTTP 포트 개방 (80 -> auto-assigned)
curl -X POST http://localhost:28000/api/v1/port_forwardings \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: token" \
  -d '{
    "internal_ip": "10.0.0.5",
    "internal_port": 80,
    "external_port": null
  }'

# 3. HTTPS 포트 개방 (443 -> 8443)
curl -X POST http://localhost:28000/api/v1/port_forwardings \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token": token" \
  -d '{
    "internal_ip": "10.0.0.5",
    "internal_port": 443,
    "external_port": 8443
  }'
```

### 시나리오 2: 데이터 볼륨 추가

```bash
# 1. 볼륨 생성
curl -X POST http://localhost:28000/api/v1/volumes \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: token" \
  -d '{
    "name": "data-vol",
    "size": 50
  }'

# 2. VM에 연결
curl -X POST http://localhost:28000/api/v1/instances/vm-123/volumes \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: token" \
  -d '{
    "volume_id": "vol-456"
  }'

# 3. 사용 후 분리
curl -X DELETE http://localhost:28000/api/v1/instances/vm-123/volumes/vol-456 \
  -H "X-Auth-Token: token"

# 4. 볼륨 삭제
curl -X DELETE http://localhost:28000/api/v1/volumes/vol-456 \
  -H "X-Auth-Token: token"
```

---

## Error Codes

| Status Code | 설명 |
|-------------|------|
| 200 | 성공 |
| 201 | 리소스 생성 성공 |
| 202 | 요청 접수 (비동기 처리) |
| 204 | 성공 (응답 본문 없음) |
| 400 | 잘못된 요청 (볼륨 연결 상태 등) |
| 401 | 인증 실패 |
| 404 | 리소스를 찾을 수 없음 |
| 500 | 서버 오류 |

---

## 참고사항

- 모든 포트포워딩 규칙은 TCP/UDP 프로토콜을 지원합니다
- 포트 범위는 10000-60000 사이에서 자동 선택됩니다
- VM 삭제 시 연결된 포트포워딩 규칙도 자동으로 제거됩니다
- 볼륨은 연결 해제 후에만 삭제 가능합니다
- Sticky IP 할당으로 VM당 포트포워딩 규칙이 같은 Floating IP에 집중됩니다
