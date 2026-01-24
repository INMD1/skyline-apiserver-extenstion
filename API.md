# Skyline API Server Extension - API Reference

## 인증 (Authentication)

모든 API 요청에는 `X-Auth-Token` 헤더가 필요합니다.

```
X-Auth-Token: your-keystone-token
```

---

## 인스턴스 (Instances)

### 인스턴스 생성
```http
POST /api/v1/instances
```

**Request Body:**
```json
{
  "name": "instance-name",
  "image_id": "image-uuid",
  "flavor_id": "flavor-uuid",
  "key_name": "keypair-name",
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

---

### 인스턴스 조회
```http
GET /api/v1/instances/{instance_id}
```

---

### 인스턴스 삭제
```http
DELETE /api/v1/instances/{instance_id}
```

**Response:** `204 No Content`

> 연결된 볼륨도 함께 삭제됩니다.

---

### 인스턴스 시작
```http
POST /api/v1/instances/{instance_id}/start
```

**Response:** `200 OK`
```json
{
  "message": "Instance started successfully",
  "instance_id": "uuid"
}
```

---

### 인스턴스 정지
```http
POST /api/v1/instances/{instance_id}/stop
```

**Response:** `200 OK`
```json
{
  "message": "Instance stopped successfully",
  "instance_id": "uuid"
}
```

---

### 인스턴스 재시작
```http
POST /api/v1/instances/{instance_id}/reboot
```

**Request Body (선택):**
```json
{
  "reboot_type": "SOFT"
}
```
- `SOFT`: 정상 재시작 (기본값)
- `HARD`: 강제 재시작

**Response:** `200 OK`
```json
{
  "message": "Instance rebooted successfully",
  "instance_id": "uuid",
  "reboot_type": "SOFT"
}
```

---

### 콘솔 URL 가져오기
```http
POST /api/v1/instances/{instance_id}/console
```

**Request Body:**
```json
{
  "console_type": "novnc"
}
```

---

## 볼륨 (Volumes)

### 볼륨 목록 조회
```http
GET /api/v1/extension/volumes
```

---

### 볼륨 삭제
```http
DELETE /api/v1/volumes/{volume_id}
```

**Response:** `204 No Content`

> 인스턴스에 연결된 볼륨은 삭제할 수 없습니다.

---

### 볼륨 연결
```http
POST /api/v1/instances/{instance_id}/volumes/attach
```

**Request Body:**
```json
{
  "volume_id": "volume-uuid"
}
```

---

### 볼륨 분리
```http
POST /api/v1/instances/{instance_id}/volumes/detach
```

**Request Body:**
```json
{
  "volume_id": "volume-uuid"
}
```

---

## 포트포워딩 (Port Forwarding)

### 포트포워딩 통계 조회
```http
GET /api/v1/port_forwardings/stats
```

---

### 포트포워딩 생성
```http
POST /api/v1/port_forwardings
```

**Request Body:**
```json
{
  "internal_ip": "192.168.1.10",
  "internal_port": 80,
  "external_port": 8080,
  "protocol": "tcp",
  "floating_ip": "xxx.xxx.xxx.xxx"
}
```

---

### 포트포워딩 삭제
```http
DELETE /api/v1/port_forwardings
```

**Request Body:**
```json
{
  "floating_ip_id": "floatingip-uuid",
  "pf_id": "port-forwarding-uuid"
}
```

**Response:** `204 No Content`

---

### 인스턴스별 포트포워딩 조회
```http
GET /api/v1/instances/{instance_id}/port_forwardings
```

---

## 이미지 (Images)

### 이미지 목록 조회
```http
GET /api/v1/images
```

---

## Flavor

### Flavor 목록 조회
```http
GET /api/v1/flavors
```

---

### Flavor 상세 조회
```http
GET /api/v1/flavors/{flavor_id}
```

---

## 키페어 (Keypairs)

### 키페어 목록 조회
```http
GET /api/v1/keypairs
```

---

### 키페어 상세 조회
```http
GET /api/v1/keypairs/{keypair_name}
```

---

### 키페어 생성
```http
POST /api/v1/keypairs
```

**Request Body:**
```json
{
  "name": "my-keypair",
  "public_key": "ssh-rsa AAAA..."
}
```

**Response:** `201 Created`

---

### 키페어 삭제
```http
DELETE /api/v1/keypairs/{keypair_name}
```

**Response:** `204 No Content`

---

## 네트워크 (Networks)

### 네트워크 목록 조회
```http
GET /api/v1/networks
```

---

## 리소스 제한 (Limits)

### 리소스 사용량 조회
```http
GET /api/v1/limits
```

---

## 서버 목록 (Extension)

### 서버 목록 조회
```http
GET /api/v1/extension/servers
```

---

### 휴지통 서버 목록 조회
```http
GET /api/v1/extension/recycle_servers
```

---

## 인증 (Login)

### 로그인
```http
POST /api/v1/login
```

---

### 프로필 조회
```http
GET /api/v1/profile
```

---

### 로그아웃
```http
POST /api/v1/logout
```

---

## 사용자 등록 (Signup)

### 회원가입
```http
POST /api/v1/signup
```

---

## 성능 모니터링 (Performance)

### 인스턴스 성능 데이터 조회
```http
GET /api/v1/instances/{instance_id}/performance
```
