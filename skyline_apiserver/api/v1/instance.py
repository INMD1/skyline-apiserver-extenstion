import asyncio
import logging
import uuid
import secrets
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import portforward_client, utils
from skyline_apiserver.client.openstack import nova, neutron, cinder
from skyline_apiserver.client.utils import get_system_session
from skyline_apiserver.config import CONF
from skyline_apiserver.db import api as db_api

LOG = logging.getLogger(__name__)


class PortForwardingRule(BaseModel):
    internal_port: int = Field(..., ge=1, le=65535)
    external_port: int = Field(..., ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"


class InstanceCreate(BaseModel):
    name: str
    image_id: Optional[str] = None
    flavor_id: str
    key_name: Optional[str] = None  # 키페어 없으면 비밀번호 로그인 모드
    network_id: str
    volume_size: Optional[int] = None
    additional_ports: Optional[List[PortForwardingRule]] = None
    os_name: Optional[str] = None


class PortForwardingAdd(BaseModel):
    internal_ip: str
    internal_port: int = Field(..., ge=1, le=65535)
    external_port: int | None = Field(None, ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"
    floating_ip: str | None = None  # Floating IP 주소 또는 UUID (선택적)


class PortForwardingDelete(BaseModel):
    floating_ip_id: str
    pf_id: str


router = APIRouter()


# tenacity 재시도 데코레이터: 외부 Proxy API 호출 시 네트워크 순단 대비
_retry_on_network_error = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=lambda retry_state: LOG.warning(
        f"[Proxy API 재시도] {retry_state.attempt_number}/3 - "
        f"오류: {retry_state.outcome.exception()}"
    ),
)


@_retry_on_network_error
async def _call_portforward_api(
    portforward_api_url: str,
    headers: dict,
    payload: dict,
) -> httpx.Response:
    """외부 포트포워딩 API POST 호출 (재시도 적용)"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(
            f"{portforward_api_url}/portforward",
            json=payload,
            headers=headers,
        )


async def setup_instance_networking(
    server_id: str,
    server_name: str,
    profile: schemas.Profile,
    additional_ports: Optional[List[PortForwardingRule]],
):
    """인스턴스 생성 후 SSH 포트포워딩을 자동 설정합니다.
    인스턴스가 ACTIVE 상태가 될 때까지 대기한 후 포트포워딩을 진행합니다."""

    session = utils.generate_session(profile)

    try:
        # 1. 인스턴스가 ACTIVE 상태가 될 때까지 대기 (최대 10분)
        LOG.info(f"[네트워크] 서버 {server_id} ACTIVE 상태 대기 시작")
        instance_active = False
        for attempt in range(60):  # 최대 10분 대기 (60 * 10초)
            try:
                server = nova.get_server(session, profile, server_id)
                server_status = server.status
                LOG.info(f"[네트워크] 서버 {server_id} 현재 상태: {server_status}")
                if server_status == "ACTIVE":
                    instance_active = True
                    break
                if server_status == "ERROR":
                    LOG.error(
                        f"[네트워크] 서버 {server_id} 상태가 ERROR입니다. 포트포워딩 중단."
                    )
                    return
            except Exception as e:
                LOG.warning(f"[네트워크] 서버 {server_id} 상태 확인 실패 (시도 {attempt + 1}/60): {e}")
            await asyncio.sleep(10)

        if not instance_active:
            LOG.error(
                f"[네트워크] 서버 {server_id}가 10분 내에 ACTIVE 상태가 되지 않았습니다. 포트포워딩 중단."
            )
            return

        LOG.info(
            f"[네트워크] 서버 {server_id} ACTIVE 상태 확인 완료. 인터페이스 준비 대기 (추가 10초)"
        )
        await asyncio.sleep(10)  # 인터페이스가 완전히 준비될 때까지 추가 대기

        # 2. VM의 Internal IP 가져오기
        internal_ip = None
        for attempt in range(10):  # 최대 100초 대기
            try:
                internal_ip = nova.get_server_internal_ip(session, profile, server_id)
                if internal_ip:
                    break
            except Exception as e:
                LOG.warning(
                    f"[네트워크] 서버 {server_id} Internal IP 조회 실패 (시도 {attempt + 1}/10): {e}"
                )
            await asyncio.sleep(10)

        if not internal_ip:
            LOG.error(f"[네트워크] 서버 {server_id}의 Internal IP를 찾을 수 없습니다.")
            return

        LOG.info(f"[네트워크] 서버 {server_id} Internal IP: {internal_ip}")

        # Portforward 서비스 API URL (환경변수 또는 기본값)
        portforward_api_url = (
            CONF.openstack.portforward_api_url or "http://localhost:8080"
        )

        # Authorization 키 가져오기
        auth_key = getattr(CONF.openstack, "portforward_authorization_key", None)

        # HTTP 헤더 준비
        headers = {"Content-Type": "application/json"}
        if auth_key:
            headers["Authorization"] = f"Bearer {auth_key}"

        # 1. SSH Port Forwarding (Automatic) - 외부 portforward API 호출
        try:
            ssh_payload = {
                "rule_name": f"ssh-{server_id[:8]}",
                "user_vm_id": server_id,
                "user_vm_name": server_name,
                "user_vm_internal_ip": internal_ip,
                "user_vm_internal_port": 22,
                "service_type": "ssh",  # SSH 전용 IP에서 할당
                "protocol": "tcp",
            }
            response = await _call_portforward_api(
                portforward_api_url, headers, ssh_payload
            )
            if response.status_code == 201:
                result = response.json()
                LOG.info(
                    f"[SSH 포트포워딩 생성 완료] 서버: {server_id}, "
                    f"외부: {result.get('proxy_external_ip')}:{result.get('proxy_external_port')} -> "
                    f"내부: {internal_ip}:22"
                )
            else:
                LOG.warning(
                    f"[SSH 포트포워딩 생성 실패] 상태: {response.status_code}, 응답: {response.text}"
                )
        except Exception as e:
            LOG.warning(f"[SSH 포트포워딩 생성 오류] 서버: {server_id}, 오류: {e}")

        # 2. Additional Ports - 외부 portforward API 호출
        if additional_ports:
            for port in additional_ports:
                try:
                    port_payload = {
                        "rule_name": f"port-{server_id[:8]}-{port.internal_port}",
                        "user_vm_id": server_id,
                        "user_vm_name": server_name,
                        "user_vm_internal_ip": internal_ip,
                        "user_vm_internal_port": port.internal_port,
                        "proxy_external_port": port.external_port or None,
                        "service_type": "other",  # 일반 포트용 IP에서 할당
                        "protocol": port.protocol,
                    }
                    response = await _call_portforward_api(
                        portforward_api_url, headers, port_payload
                    )
                    if response.status_code == 201:
                        LOG.info(
                            f"[추가 포트포워딩 생성 완료] 서버: {server_id}, 포트: {port.internal_port}"
                        )
                    else:
                        LOG.warning(
                            f"[추가 포트포워딩 생성 실패] 포트: {port.internal_port}, 상태: {response.status_code}"
                        )
                except Exception as e:
                    LOG.warning(
                        f"[추가 포트포워딩 생성 오류] 포트: {port.internal_port}, 오류: {e}"
                    )

    except Exception as e:
        LOG.error(f"[네트워크] 서버 {server_id} 네트워크 설정 실패: {e}")


@router.post("/instances", status_code=status.HTTP_202_ACCEPTED)
async def create_instance(
    instance: InstanceCreate,
    background_tasks: BackgroundTasks,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)

    # 중복 이름 체크: 같은 프로젝트 내에서 동일한 이름의 인스턴스가 있는지 확인
    existing_servers = nova.list_servers(
        profile=profile,
        session=session,
        global_request_id="",
        search_opts={"name": f"^{instance.name}$", "project_id": profile.project.id},
    )
    for server in existing_servers:
        if server.name == instance.name:
            LOG.warning(
                f"[인스턴스 생성 거부] 중복 이름: '{instance.name}', 사용자: {profile.user.name}"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"이미 동일한 이름의 인스턴스가 존재합니다: '{instance.name}'",
            )

    # 인스턴스 요청을 DB 같은 데 먼저 기록 (id 미리 생성)
    request_id = str(uuid.uuid4())
    LOG.info(
        f"[인스턴스 생성] 사용자: {profile.user.name}, 프로젝트: {profile.project.name}, 요청ID: {request_id}, 인스턴스명: {instance.name}"
    )

    # DB에 활동 기록
    db_api.create_activity_record(
        user_id=profile.user.id,
        project_id=profile.project.id,
        category="인스턴스 생성",
        message=f"인스턴스 '{instance.name}' 생성 요청 (요청ID: {request_id})",
        status="pending",
        token="",  # 보안을 위해 토큰 저장 제거
    )

    # 실제 생성 로직은 백그라운드 태스크로 돌림 (async 함수이므로 이벤트 루프에서 실행됨)
    background_tasks.add_task(
        _provision_instance, session, profile, instance, request_id
    )

    # 202 Accepted 와 요청 ID, 인스턴스 이름 반환
    return {
        "request_id": request_id,
        "status": "PENDING",
        "instance_name": instance.name,
    }


async def _provision_instance(session, profile, instance: InstanceCreate, request_id: str):
    try:
        default_user = "cloud-user"
        default_password = secrets.token_urlsafe(12)
        instance_meta = {"os_name": instance.os_name} if instance.os_name else {}

        # OS별 기본 유저 매핑
        if instance.os_name:
            os_lower = instance.os_name.lower()
            if "ubuntu" in os_lower:
                default_user = "ubuntu"
            elif "debian" in os_lower:
                default_user = "debian"
            elif "rocky" in os_lower:
                default_user = "rocky"
            elif "alpine" in os_lower:
                default_user = "alpine"

        # OS 무관하게 항상 비밀번호 SSH 활성화 userdata 적용
        # Ubuntu 등은 /etc/ssh/sshd_config.d/ override 파일이
        # PasswordAuthentication no를 강제하므로 write_files로 덮어씀
        userdata_payload = (
            f"#cloud-config\n"
            f"ssh_pwauth: true\n"
            f"chpasswd:\n"
            f"  list: |\n"
            f"    {default_user}:{default_password}\n"
            f"  expire: false\n"
            f"write_files:\n"
            f"  - path: /etc/ssh/sshd_config.d/99-password-auth.conf\n"
            f"    content: |\n"
            f"      PasswordAuthentication yes\n"
            f"      KbdInteractiveAuthentication yes\n"
            f"      ChallengeResponseAuthentication yes\n"
            f"    owner: root:root\n"
            f"    permissions: '0644'\n"
            f"runcmd:\n"
            f"  # sshd_config 본체도 수정 (override 디렉터리가 없는 구형 OS 대비)\n"
            f"  - sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config\n"
            f"  - sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config\n"
            f"  - sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication yes/' /etc/ssh/sshd_config\n"
            f"  # sshd_config.d 내 기존 override 파일도 일괄 처리\n"
            f"  - for f in /etc/ssh/sshd_config.d/*.conf; do [ -f \"$f\" ] && sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' \"$f\"; done\n"
            f"  # sshd 재시작 (systemd / OpenRC / SysV 모두 대응)\n"
            f"  - if command -v systemctl > /dev/null 2>&1; then systemctl restart sshd || systemctl restart ssh; elif command -v rc-service > /dev/null 2>&1; then rc-service sshd restart; else service sshd restart 2>/dev/null || service ssh restart; fi\n"
        )
        instance_meta["default_user"] = default_user
        instance_meta["default_password"] = default_password

        if instance.volume_size:
            if not instance.image_id:
                raise ValueError("Image ID required for bootable volume.")

            volume = cinder.create_volume(
                session=session,
                profile=profile,
                name=f"{instance.name}-root",
                size=instance.volume_size,
                image_id=instance.image_id,
            )

            # 볼륨 준비 기다리기
            for attempt in range(120):
                vol_status = cinder.get_volume(session, profile, volume.id).status
                if vol_status == "available":
                    break
                if vol_status == "error":
                    raise RuntimeError(f"Volume {volume.id} entered ERROR state.")
                await asyncio.sleep(10)
            else:
                raise RuntimeError("Volume creation timed out.")

            server = nova.create_instance_from_volume(
                session=session,
                profile=profile,
                name=instance.name,
                volume_id=volume.id,
                flavor_id=instance.flavor_id,
                net_id=instance.network_id,
                key_name=instance.key_name,
                security_groups=["all-internal-allow"],
                meta=instance_meta,
                userdata=userdata_payload,
            )
            LOG.info(
                f"[인스턴스 생성 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}, 볼륨ID: {volume.id}"
            )
        else:
            if not instance.image_id:
                raise ValueError("Image ID required when not booting from a volume.")

            server = nova.create_instance_with_network(
                session=session,
                profile=profile,
                name=instance.name,
                image_id=instance.image_id,
                flavor_id=instance.flavor_id,
                net_id=instance.network_id,
                key_name=instance.key_name,
                security_groups=["all-internal-allow"],
                meta=instance_meta,
                userdata=userdata_payload,
            )
            LOG.info(
                f"[인스턴스 생성 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}"
            )

        # 추가 네트워크 세팅
        await setup_instance_networking(
            server.id, instance.name, profile, instance.additional_ports
        )

        # 인스턴스 라이프사이클 레코드 등록 (수명 관리 기능이 켜져 있을 때)
        # admin 프로젝트 인스턴스는 예외 처리
        try:
            from skyline_apiserver.config import CONF as _CONF
            lc_enabled_row = db_api.get_setting("instance_lifecycle_enabled")
            lc_enabled = lc_enabled_row.value if lc_enabled_row else _CONF.setting.instance_lifecycle_enabled
            is_admin_project = (profile.project.name == _CONF.openstack.system_project)
            if lc_enabled and not is_admin_project:
                import time as _time
                lifetime_row = db_api.get_setting("instance_lifetime_days")
                lifetime_days = int(lifetime_row.value if lifetime_row else _CONF.setting.instance_lifetime_days)
                now_ts = int(_time.time())
                db_api.create_instance_lifecycle(
                    instance_id=server.id,
                    instance_name=instance.name,
                    user_id=profile.user.id,
                    project_id=profile.project.id,
                    user_email=getattr(profile.user, "email", "") or "",
                    created_at=now_ts,
                    expires_at=now_ts + lifetime_days * 86400,
                )
                LOG.info(f"[Lifecycle] 라이프사이클 레코드 생성: instance={server.id}, lifetime={lifetime_days}일")
            elif is_admin_project:
                LOG.info(f"[Lifecycle] admin 프로젝트 인스턴스 — 수명 관리 제외: instance={server.id}")
        except Exception as lc_exc:
            LOG.warning(f"[Lifecycle] 라이프사이클 레코드 생성 실패 (무시): {lc_exc}")

        # 성공 기록 (DB 업데이트 같은 것)
        LOG.info(f"[프로비저닝 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}")

    except Exception as e:
        LOG.error(f"[인스턴스 생성 실패] 요청ID: {request_id}, 오류: {e}")


@router.get("/instances/{instance_id}")
def get_instance(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    try:
        server = nova.get_server(session, profile, instance_id)

        # Convert to dict for manipulation
        server_dict = {
            "id": server.id,
            "name": server.name,
            "status": server.status,
            "created": server.created,
            "updated": server.updated,
            "flavor": getattr(server, "flavor", {}),
            "image": server.image if server.image != "" else None,
            "addresses": server.addresses,
        }

        # Get internal IP
        internal_ip = None
        for network in server.addresses:
            for ip in server.addresses[network]:
                if ip.get("OS-EXT-IPS:type") == "fixed":
                    internal_ip = ip["addr"]
                    break
            if internal_ip:
                break

        # OS 정보 및 초기 자격 증명 추가
        if server.metadata:
            try:
                server_dict["os_name"] = server.metadata.get("os_name", "Unknown")
                server_dict["default_user"] = server.metadata.get("default_user")
                server_dict["default_password"] = server.metadata.get("default_password")
            except Exception as e:
                LOG.warning(f"Failed to get OS info for instance {instance_id}: {e}")
                server_dict["os_name"] = "Unknown"
        else:
            server_dict["os_name"] = "Unknown"

        return server_dict
    except Exception as e:
        LOG.error(f"Failed to get instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get instance")


@router.get("/port_forwardings/stats")
def get_port_forwarding_stats(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """현재 사용자의 VM에서 사용 중인 포트포워딩 통계를 반환합니다."""
    try:
        session = utils.generate_session(profile)

        # 현재 사용자의 VM 목록에서 Internal IP 수집
        servers = nova.list_servers(
            profile=profile,
            session=session,
            global_request_id="",
            search_opts={"project_id": profile.project.id},
        )
        user_internal_ips = set()
        for server in servers:
            for network in server.addresses.values():
                for ip_info in network:
                    if ip_info.get("OS-EXT-IPS:type") == "fixed":
                        user_internal_ips.add(ip_info["addr"])

        # 시스템 세션으로 포트포워딩 조회
        system_session = get_system_session()
        nc = utils.neutron_client(session=system_session, region=profile.region)

        total_port_forwardings = 0
        user_port_forwardings = []

        # 모든 floating IP에서 포트포워딩 조회
        all_fips = nc.list_floatingips().get("floatingips", [])
        for fip in all_fips:
            try:
                # 해당 floating IP의 포트포워딩 조회
                pfs = nc.list_port_forwardings(floatingip=fip["id"]).get(
                    "port_forwardings", []
                )

                for pf in pfs:
                    internal_ip = pf.get("internal_ip_address")
                    # 현재 사용자의 VM IP인 경우만 카운트
                    if internal_ip in user_internal_ips:
                        total_port_forwardings += 1
                        user_port_forwardings.append(
                            {
                                "id": pf.get("id"),
                                "floating_ip_id": fip["id"],
                                "floating_ip_address": fip["floating_ip_address"],
                                "internal_ip_address": internal_ip,
                                "internal_port": pf.get("internal_port"),
                                "external_port": pf.get("external_port"),
                                "protocol": pf.get("protocol"),
                            }
                        )
            except Exception as e:
                LOG.warning(f"[포트포워딩 통계] Floating IP {fip['id']} 조회 실패: {e}")
                continue

        return {
            "total_count": total_port_forwardings,
            "limit": CONF.openstack.port_forwarding_limit,
            "remaining": max(
                0, CONF.openstack.port_forwarding_limit - total_port_forwardings
            ),
            "port_forwardings": user_port_forwardings,
        }
    except Exception as e:
        LOG.error(f"Failed to get port forwarding stats: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get port forwarding stats"
        )


@router.post("/port_forwardings")
def add_port_forwarding(
    pf_request: PortForwardingAdd,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    try:
        all_fips = neutron.list_floatingips(
            session, profile, tenant_id=profile.project.id
        )["floatingips"]
        port_forwardings_used = 0
        for fip_item in all_fips:
            pfs = neutron.get_port_forwarding_rules(
                session, profile.region, fip_item["id"]
            )
            port_forwardings_used += len(pfs)

        if port_forwardings_used >= CONF.openstack.port_forwarding_limit:
            raise HTTPException(
                status_code=400,
                detail="Maximum number of port forwardings for the project has been reached.",
            )

        # Floating IP 선택: 사용자 지정 또는 자동 선택
        fip = None  # 초기화
        if pf_request.floating_ip:
            # 사용자가 floating IP를 직접 지정한 경우
            nc = utils.neutron_client(session=session, region=profile.region)

            # UUID 형식인지 IP 주소인지 확인
            if (
                len(pf_request.floating_ip) == 36
                and pf_request.floating_ip.count("-") == 4
            ):
                # UUID로 조회
                fip = nc.show_floatingip(pf_request.floating_ip)["floatingip"]
            else:
                # IP 주소로 조회
                all_fips_list = nc.list_floatingips().get("floatingips", [])
                for f in all_fips_list:
                    if f.get("floating_ip_address") == pf_request.floating_ip:
                        fip = f
                        break
                if not fip:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Floating IP not found: {pf_request.floating_ip}",
                    )
        else:
            raise HTTPException(
                status_code=400,
                detail="floating_ip is required. Please specify a floating IP address or UUID.",
            )

        # floatingip_id는 UUID여야 함 (IP 주소 아님!)
        fip_id = fip["id"]

        # 시스템 세션 사용 (floating IP가 다른 프로젝트에 있을 수 있음)
        system_session = get_system_session()

        pf = neutron.create_port_forwarding_rule(
            session=system_session,  # 시스템 세션 사용!
            region=profile.region,
            floatingip_id=fip_id,
            internal_ip_address=pf_request.internal_ip,
            internal_port=pf_request.internal_port,
            external_port=pf_request.external_port,  # Can be None for auto-assignment
            protocol=pf_request.protocol,
        )

        # 응답에 floating IP 주소 포함
        response = {
            "message": "Port forwarding created successfully",
            "port_forwarding": {
                "id": pf.get("id"),
                "floating_ip_address": fip.get("floating_ip_address"),  # IP 주소만
                "internal_ip_address": pf.get("internal_ip_address"),
                "internal_port": pf.get("internal_port"),
                "external_port": pf.get("external_port"),
                "protocol": pf.get("protocol"),
            },
        }
        return response
    except Exception as e:
        LOG.error(f"Failed to create port forwarding: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to create port forwarding"
        )


@router.delete("/port_forwardings", status_code=status.HTTP_204_NO_CONTENT)
def delete_port_forwarding(
    pf_delete: PortForwardingDelete,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    try:
        neutron.delete_port_forwarding_rule(
            session=session,
            region=profile.region,
            floatingip_id=pf_delete.floating_ip_id,
            pf_id=pf_delete.pf_id,
        )
        return
    except Exception as e:
        LOG.error(f"Failed to delete port forwarding: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to delete port forwarding"
        )


@router.get("/instances/{instance_id}/port_forwardings")
def list_instance_port_forwardings(
    instance_id: str, profile: schemas.Profile = Depends(deps.get_profile_from_header)
):
    """
    특정 VM의 모든 포트포워딩 규칙을 조회합니다.
    """
    session = utils.generate_session(profile)
    try:
        # VM의 internal IP 가져오기
        internal_ip = nova.get_server_internal_ip(session, profile, instance_id)

        # 해당 IP의 모든 포트포워딩 규칙 조회
        pfs = neutron.get_port_forwardings_by_internal_ip(
            session, profile.region, internal_ip
        )

        return {
            "instance_id": instance_id,
            "internal_ip": internal_ip,
            "port_forwardings": pfs,
        }
    except Exception as e:
        LOG.error(f"Failed to list port forwardings for instance {instance_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to list port forwardings"
        )


class ConsoleRequest(BaseModel):
    console_type: str


@router.post("/instances/{instance_id}/console")
def get_instance_console(
    instance_id: str,
    console_request: ConsoleRequest,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    try:
        console_data = nova.get_console_url(
            session, profile, instance_id, console_request.console_type
        )
        return console_data
    except Exception as e:
        LOG.error(f"Failed to get console URL for instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get console URL"
        )


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    background_tasks: BackgroundTasks,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스를 삭제합니다. 연결된 볼륨과 포트포워딩 규칙도 함께 삭제됩니다.
    """
    session = utils.generate_session(profile)

    try:
        # 0-a. 외부 포트포워딩 서비스 규칙 정리 (외부 Proxy VM 서비스)
        try:
            ext_pfs = await portforward_client.get_portforwardings_by_vm(instance_id)
            if ext_pfs:
                LOG.info(
                    f"[외부 포트포워딩 정리] 인스턴스 {instance_id} 관련 외부 규칙 {len(ext_pfs)}개 삭제 시작"
                )
                for ext_pf in ext_pfs:
                    try:
                        rule_id = ext_pf.get("id") or ext_pf.get("rule_id")
                        if rule_id:
                            await portforward_client.delete_portforwarding(rule_id)
                            LOG.info(f"[외부 포트포워딩 삭제 완료] rule_id: {rule_id}")
                    except Exception as ext_err:
                        LOG.warning(
                            f"[외부 포트포워딩 삭제 실패] rule_id: {ext_pf.get('id')}, 오류: {ext_err}"
                        )
                LOG.info("[외부 포트포워딩 정리] 완료")
        except Exception as e:
            LOG.warning(f"인스턴스 삭제 전 외부 포트포워딩 정리 중 오류 발생: {e}")

        # 0-b. OpenStack Neutron 포트포워딩 규칙 정리
        try:
            internal_ip = nova.get_server_internal_ip(session, profile, instance_id)
            if internal_ip:
                pfs = neutron.get_port_forwardings_by_internal_ip(
                    session, profile.region, internal_ip
                )
                if pfs:
                    LOG.info(
                        f"[Neutron 포트포워딩 정리] 인스턴스 {instance_id} ({internal_ip}) 관련 규칙 {len(pfs)}개 삭제 시작"
                    )
                    system_session = get_system_session()

                    for pf in pfs:
                        try:
                            neutron.delete_port_forwarding_rule(
                                session=system_session,
                                region=profile.region,
                                floatingip_id=pf["floating_ip_id"],
                                pf_id=pf["id"],
                            )
                        except Exception as ignore:
                            LOG.warning(
                                f"Neutron 포트포워딩 규칙 삭제 실패 (ID: {pf.get('id')}): {ignore}"
                            )
                    LOG.info("[Neutron 포트포워딩 정리] 완료")
        except Exception as e:
            LOG.warning(f"인스턴스 삭제 전 Neutron 포트포워딩 정리 중 오류 발생: {e}")

        # 1. 인스턴스에 연결된 볼륨 목록 가져오기
        attached_volumes = nova.get_server_volumes(session, profile, instance_id)
        volume_ids = [vol.volumeId for vol in attached_volumes]

        # 2. 인스턴스 삭제
        LOG.info(
            f"[인스턴스 삭제] 사용자: {profile.user.name}, 프로젝트: {profile.project.name}, 인스턴스ID: {instance_id}, 연결된볼륨: {volume_ids}"
        )
        nova.delete_server(session, profile, instance_id)

        # DB에 활동 기록
        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 삭제",
            message=f"인스턴스 '{instance_id}' 삭제 (볼륨: {volume_ids})",
            status="success",
            token="",  # 보안을 위해 토큰 저장 제거
        )

        # 3. 볼륨 삭제는 백그라운드에서 처리 (인스턴스가 완전히 삭제된 후 삭제해야 함)
        if volume_ids:
            background_tasks.add_task(
                _delete_volumes_after_instance,
                session,
                profile,
                instance_id,
                volume_ids,
            )

        # 4. 라이프사이클 레코드 정리
        try:
            db_api.delete_instance_lifecycle(instance_id)
        except Exception as lc_exc:
            LOG.warning(f"[Lifecycle] 라이프사이클 레코드 삭제 실패 (무시): {lc_exc}")

        return
    except Exception as e:
        LOG.error(f"Failed to delete instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete instance",
        )


async def _delete_volumes_after_instance(
    session, profile, instance_id: str, volume_ids: list
):
    """인스턴스가 삭제된 후 볼륨을 삭제하는 백그라운드 태스크"""
    # 인스턴스가 완전히 삭제될 때까지 대기 (최대 2분)
    for attempt in range(24):
        try:
            nova.get_server(session, profile, instance_id)
            # 아직 인스턴스가 존재하면 대기
            await asyncio.sleep(5)
        except Exception as e:
            # 인스턴스가 삭제됨 (404 등)
            LOG.info(f"[볼륨 정리] 인스턴스 {instance_id} 삭제 확인 (시도 {attempt + 1}): {e}")
            break

    # 볼륨이 available 상태가 될 때까지 대기 후 삭제
    for volume_id in volume_ids:
        try:
            # 볼륨이 available 상태가 될 때까지 대기 (최대 1분)
            for attempt in range(12):
                try:
                    volume = cinder.get_volume(session, profile, volume_id)
                    if volume.status == "available":
                        break
                    await asyncio.sleep(5)
                except Exception as e:
                    # 볼륨이 이미 삭제됨
                    LOG.info(f"[볼륨 정리] 볼륨 {volume_id} 상태 확인 불가 (이미 삭제됨?): {e}")
                    break

            # 볼륨 삭제
            cinder.delete_volume(session, profile, volume_id)
            LOG.info(f"[볼륨 삭제 완료] 인스턴스ID: {instance_id}, 볼륨ID: {volume_id}")
        except Exception as e:
            LOG.error(f"[볼륨 삭제 실패] 볼륨ID: {volume_id}, 오류: {e}")


class VolumeAction(BaseModel):
    volume_id: str


@router.post("/instances/{instance_id}/volumes/attach", status_code=status.HTTP_200_OK)
def attach_volume(
    instance_id: str,
    volume_action: VolumeAction,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스에 볼륨을 연결합니다.
    """
    session = utils.generate_session(profile)
    try:
        nova.attach_volume_to_server(
            session=session,
            profile=profile,
            server_id=instance_id,
            volume_id=volume_action.volume_id,
        )
        LOG.info(
            f"[볼륨 연결] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 볼륨ID: {volume_action.volume_id}"
        )
        return {
            "message": "Volume attached successfully",
            "volume_id": volume_action.volume_id,
        }
    except Exception as e:
        LOG.error(f"Failed to attach volume {volume_action.volume_id} to instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to attach volume",
        )


@router.post("/instances/{instance_id}/volumes/detach", status_code=status.HTTP_200_OK)
def detach_volume(
    instance_id: str,
    volume_action: VolumeAction,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스에서 볼륨을 분리합니다.
    """
    session = utils.generate_session(profile)
    try:
        nova.detach_volume_from_server(
            session=session,
            profile=profile,
            server_id=instance_id,
            volume_id=volume_action.volume_id,
        )
        LOG.info(
            f"[볼륨 분리] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 볼륨ID: {volume_action.volume_id}"
        )
        return {
            "message": "Volume detached successfully",
            "volume_id": volume_action.volume_id,
        }
    except Exception as e:
        LOG.error(f"Failed to detach volume {volume_action.volume_id} from instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to detach volume",
        )


@router.post("/instances/{instance_id}/start", status_code=status.HTTP_200_OK)
def start_instance(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스를 시작합니다.
    """
    session = utils.generate_session(profile)
    try:
        nova.start_server(session, profile, instance_id)
        LOG.info(
            f"[인스턴스 시작] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}"
        )

        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 시작",
            message=f"인스턴스 '{instance_id}' 시작",
            status="success",
            token="",  # 보안을 위해 토큰 저장 제거
        )
        return {"message": "Instance started successfully", "instance_id": instance_id}
    except Exception as e:
        LOG.error(f"Failed to start instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start instance",
        )


@router.post("/instances/{instance_id}/stop", status_code=status.HTTP_200_OK)
def stop_instance(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스를 정지합니다.
    """
    session = utils.generate_session(profile)
    try:
        nova.stop_server(session, profile, instance_id)
        LOG.info(
            f"[인스턴스 정지] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}"
        )

        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 정지",
            message=f"인스턴스 '{instance_id}' 정지",
            status="success",
            token="",  # 보안을 위해 토큰 저장 제거
        )
        return {"message": "Instance stopped successfully", "instance_id": instance_id}
    except Exception as e:
        LOG.error(f"Failed to stop instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop instance",
        )


class RebootRequest(BaseModel):
    reboot_type: Literal["SOFT", "HARD"] = "SOFT"


@router.post("/instances/{instance_id}/reboot", status_code=status.HTTP_200_OK)
def reboot_instance(
    instance_id: str,
    reboot_request: RebootRequest = RebootRequest(),
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스를 재시작합니다. reboot_type: SOFT (기본값) 또는 HARD
    """
    session = utils.generate_session(profile)
    try:
        nova.reboot_server(session, profile, instance_id, reboot_request.reboot_type)
        LOG.info(
            f"[인스턴스 재시작] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 타입: {reboot_request.reboot_type}"
        )

        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 재시작",
            message=f"인스턴스 '{instance_id}' 재시작 (타입: {reboot_request.reboot_type})",
            status="success",
            token="",  # 보안을 위해 토큰 저장 제거
        )
        return {
            "message": "Instance rebooted successfully",
            "instance_id": instance_id,
            "reboot_type": reboot_request.reboot_type,
        }
    except Exception as e:
        LOG.error(f"Failed to reboot instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reboot instance",
        )
