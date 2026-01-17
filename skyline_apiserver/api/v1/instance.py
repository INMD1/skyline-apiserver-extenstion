from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import logging

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import nova, neutron, cinder
from skyline_apiserver.db import api as db_api
import random
import time
import uuid

LOG = logging.getLogger(__name__)


class PortForwardingRule(BaseModel):
    internal_port: int
    external_port: int
    protocol: str = "tcp"


class InstanceCreate(BaseModel):
    name: str
    image_id: Optional[str] = None
    flavor_id: str
    key_name: str
    network_id: str
    volume_size: Optional[int] = None
    additional_ports: Optional[List[PortForwardingRule]] = None


class PortForwardingAdd(BaseModel):
    internal_ip: str
    internal_port: int
    external_port: int | None = None
    protocol: str = "tcp"
    floating_ip: str | None = None  # Floating IP 주소 또는 UUID (선택적)


class PortForwardingDelete(BaseModel):
    floating_ip_id: str
    pf_id: str


router = APIRouter()


from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks


def setup_instance_networking(
    server_id: str,
    profile: schemas.Profile,
    additional_ports: Optional[List[PortForwardingRule]],
):
    session = utils.generate_session(profile)
    
    # 시스템 세션 사용 (다른 프로젝트의 floating IP에 포트포워딩 생성)
    from skyline_apiserver.client.utils import get_system_session
    system_session = get_system_session()
    
    try:
        internal_ip = nova.get_server_internal_ip(session, profile, server_id)
        ssh_fip = neutron.find_floating_ip_for_ssh(session, profile.region)
        ssh_fip_id = ssh_fip["id"]

        # Auto-assign SSH port using random port allocation
        neutron.create_port_forwarding_rule(
            session=system_session,  # 시스템 세션 사용
            region=profile.region,
            floatingip_id=ssh_fip_id,
            internal_ip_address=internal_ip,
            internal_port=22,
            external_port=random.randrange(1, 600),
        )

        if additional_ports:
            fip = neutron.find_portforward_floating_ip(session, profile.region)
            fip_id = fip["id"]
            for port in additional_ports:
                neutron.create_port_forwarding_rule(
                    session=system_session,  # 시스템 세션 사용
                    region=profile.region,
                    floatingip_id=fip_id,
                    internal_ip_address=internal_ip,
                    internal_port=port.internal_port,
                    external_port=port.external_port if port.external_port else None,  # Auto-assign if not provided
                    protocol=port.protocol,
                )
    except Exception as e:
        # You might want to log this error or update the server status to ERROR
        LOG.error(f"[네트워크] 서버 {server_id} 네트워크 설정 실패: {e}")


@router.post("/instances", status_code=status.HTTP_202_ACCEPTED)
def create_instance(
    instance: InstanceCreate,
    background_tasks: BackgroundTasks,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)

    # 인스턴스 요청을 DB 같은 데 먼저 기록 (id 미리 생성)
    request_id = str(uuid.uuid4())
    LOG.info(f"[인스턴스 생성] 사용자: {profile.user.name}, 프로젝트: {profile.project.name}, 요청ID: {request_id}, 인스턴스명: {instance.name}")
    
    # DB에 활동 기록
    db_api.create_activity_record(
        user_id=profile.user.id,
        project_id=profile.project.id,
        category="인스턴스 생성",
        message=f"인스턴스 '{instance.name}' 생성 요청 (요청ID: {request_id})",
        status="pending",
        token=profile.keystone_token[:32] if profile.keystone_token else "",
    )

    # 실제 생성 로직은 백그라운드 태스크로 돌림
    background_tasks.add_task(
        _provision_instance, session, profile, instance, request_id
    )

    # 202 Accepted 와 요청 ID 반환
    return {"request_id": request_id, "status": "PENDING"}


def _provision_instance(session, profile, instance: InstanceCreate, request_id: str):
    try:
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
            for _ in range(120):
                vol_status = cinder.get_volume(session, profile, volume.id).status
                if vol_status == "available":
                    break
                time.sleep(10)
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
            )
            LOG.info(f"[인스턴스 생성 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}, 볼륨ID: {volume.id}")
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
            )
            LOG.info(f"[인스턴스 생성 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}")

        # 추가 네트워크 세팅도 백그라운드로
        setup_instance_networking(server.id, profile, instance.additional_ports)

        # 성공 기록 (DB 업데이트 같은 것)
        LOG.info(f"[프로비저닝 완료] 요청ID: {request_id}, 인스턴스ID: {server.id}")

    except Exception as e:
        LOG.error(f"[인스턴스 생성 실패] 요청ID: {request_id}, 오류: {e}")


from skyline_apiserver.config import CONF


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
        
        # Add port forwarding information
        if internal_ip:
            port_forwardings = neutron.get_port_forwardings_by_internal_ip(session, profile.region, internal_ip)
            server_dict["port_forwardings"] = port_forwardings
        else:
            server_dict["port_forwardings"] = []
        
        return server_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



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
            search_opts={"project_id": profile.project.id}
        )
        user_internal_ips = set()
        for server in servers:
            for network in server.addresses.values():
                for ip_info in network:
                    if ip_info.get("OS-EXT-IPS:type") == "fixed":
                        user_internal_ips.add(ip_info["addr"])

        
        # 시스템 세션으로 포트포워딩 조회
        from skyline_apiserver.client.utils import get_system_session
        system_session = get_system_session()
        nc = utils.neutron_client(session=system_session, region=profile.region)
        
        # 설정된 포트포워딩 IP 목록
        configured_fip_ids = CONF.openstack.portforward_floating_ip_ids
        
        total_port_forwardings = 0
        user_port_forwardings = []
        all_pfs_found = []  # 디버그용: 모든 포트포워딩
        
        # 설정된 floating IP들에서 포트포워딩 조회
        for fip_id_or_ip in configured_fip_ids:
            try:
                # UUID 형식인지 확인
                if len(fip_id_or_ip) == 36 and fip_id_or_ip.count('-') == 4:
                    fip = nc.show_floatingip(fip_id_or_ip)["floatingip"]
                else:
                    # IP 주소로 검색
                    all_fips = nc.list_floatingips().get("floatingips", [])
                    fip = None
                    for f in all_fips:
                        if f.get("floating_ip_address") == fip_id_or_ip:
                            fip = f
                            break
                    if not fip:
                        continue
                
                # 해당 floating IP의 포트포워딩 조회
                pfs = nc.list_port_forwardings(floatingip=fip["id"]).get("port_forwardings", [])
                
                for pf in pfs:
                    internal_ip = pf.get("internal_ip_address")
                    all_pfs_found.append({
                        "fip": fip["floating_ip_address"],
                        "internal_ip": internal_ip,
                        "external_port": pf.get("external_port"),
                    })
                    # 현재 사용자의 VM IP인 경우만 카운트
                    if internal_ip in user_internal_ips:
                        total_port_forwardings += 1
                        user_port_forwardings.append({
                            "id": pf.get("id"),
                            "floating_ip_id": fip["id"],
                            "floating_ip_address": fip["floating_ip_address"],
                            "internal_ip_address": internal_ip,
                            "internal_port": pf.get("internal_port"),
                            "external_port": pf.get("external_port"),
                            "protocol": pf.get("protocol"),
                        })
            except Exception as e:
                all_pfs_found.append({"error": str(e), "fip": fip_id_or_ip})
                continue
        
        return {
            "total_count": total_port_forwardings,
            "limit": CONF.openstack.port_forwarding_limit,
            "remaining": max(0, CONF.openstack.port_forwarding_limit - total_port_forwardings),
            "port_forwardings": user_port_forwardings,
            "_debug": {
                "user_vm_ips": list(user_internal_ips),
                "configured_fip_ids": configured_fip_ids,
                "all_pfs_found": all_pfs_found,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get port forwarding stats: {e}")




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
            if len(pf_request.floating_ip) == 36 and pf_request.floating_ip.count('-') == 4:
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
                        detail=f"Floating IP not found: {pf_request.floating_ip}"
                    )
        else:
            # 설정 파일에서 자동 선택
            fip = neutron.find_portforward_floating_ip(session, profile.region)
        
        # floatingip_id는 UUID여야 함 (IP 주소 아님!)
        fip_id = fip["id"]

        # 시스템 세션 사용 (floating IP가 다른 프로젝트에 있을 수 있음)
        from skyline_apiserver.client.utils import get_system_session
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
            }
        }
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create port forwarding: {e}")




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
        raise HTTPException(
            status_code=500, detail=f"Failed to delete port forwarding: {e}"
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
        raise HTTPException(
            status_code=500, detail=f"Failed to list port forwardings: {e}"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instance(
    instance_id: str,
    background_tasks: BackgroundTasks,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    인스턴스를 삭제합니다. 연결된 볼륨도 함께 삭제됩니다.
    """
    session = utils.generate_session(profile)
    
    try:
        # 1. 인스턴스에 연결된 볼륨 목록 가져오기
        attached_volumes = nova.get_server_volumes(session, profile, instance_id)
        volume_ids = [vol.volumeId for vol in attached_volumes]
        # 2. 인스턴스 삭제
        LOG.info(f"[인스턴스 삭제] 사용자: {profile.user.name}, 프로젝트: {profile.project.name}, 인스턴스ID: {instance_id}, 연결된볼륨: {volume_ids}")
        nova.delete_server(session, profile, instance_id)
        
        # DB에 활동 기록
        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 삭제",
            message=f"인스턴스 '{instance_id}' 삭제 (볼륨: {volume_ids})",
            status="success",
            token=profile.keystone_token[:32] if profile.keystone_token else "",
        )
        
        # 3. 볼륨 삭제는 백그라운드에서 처리 (인스턴스가 완전히 삭제된 후 삭제해야 함)
        if volume_ids:
            background_tasks.add_task(
                _delete_volumes_after_instance, session, profile, instance_id, volume_ids
            )
        
        return
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete instance: {e}",
        )


def _delete_volumes_after_instance(session, profile, instance_id: str, volume_ids: list):
    """인스턴스가 삭제된 후 볼륨을 삭제하는 백그라운드 태스크"""
    import time
    
    # 인스턴스가 완전히 삭제될 때까지 대기 (최대 2분)
    for _ in range(24):
        try:
            nova.get_server(session, profile, instance_id)
            # 아직 인스턴스가 존재하면 대기
            time.sleep(5)
        except:
            # 인스턴스가 삭제됨
            break
    
    # 볼륨이 available 상태가 될 때까지 대기 후 삭제
    for volume_id in volume_ids:
        try:
            # 볼륨이 available 상태가 될 때까지 대기 (최대 1분)
            for _ in range(12):
                try:
                    volume = cinder.get_volume(session, profile, volume_id)
                    if volume.status == "available":
                        break
                    time.sleep(5)
                except:
                    # 볼륨이 이미 삭제됨
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
        result = nova.attach_volume_to_server(
            session=session,
            profile=profile,
            server_id=instance_id,
            volume_id=volume_action.volume_id,
        )
        LOG.info(f"[볼륨 연결] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 볼륨ID: {volume_action.volume_id}")
        return {"message": "Volume attached successfully", "volume_id": volume_action.volume_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to attach volume: {e}",
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
        LOG.info(f"[볼륨 분리] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 볼륨ID: {volume_action.volume_id}")
        return {"message": "Volume detached successfully", "volume_id": volume_action.volume_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detach volume: {e}",
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
        LOG.info(f"[인스턴스 시작] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}")
        
        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 시작",
            message=f"인스턴스 '{instance_id}' 시작",
            status="success",
            token=profile.keystone_token[:32] if profile.keystone_token else "",
        )
        return {"message": "Instance started successfully", "instance_id": instance_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start instance: {e}",
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
        LOG.info(f"[인스턴스 정지] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}")
        
        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 정지",
            message=f"인스턴스 '{instance_id}' 정지",
            status="success",
            token=profile.keystone_token[:32] if profile.keystone_token else "",
        )
        return {"message": "Instance stopped successfully", "instance_id": instance_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop instance: {e}",
        )


class RebootRequest(BaseModel):
    reboot_type: str = "SOFT"  # SOFT or HARD


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
        LOG.info(f"[인스턴스 재시작] 사용자: {profile.user.name}, 인스턴스ID: {instance_id}, 타입: {reboot_request.reboot_type}")
        
        db_api.create_activity_record(
            user_id=profile.user.id,
            project_id=profile.project.id,
            category="인스턴스 재시작",
            message=f"인스턴스 '{instance_id}' 재시작 (타입: {reboot_request.reboot_type})",
            status="success",
            token=profile.keystone_token[:32] if profile.keystone_token else "",
        )
        return {"message": "Instance rebooted successfully", "instance_id": instance_id, "reboot_type": reboot_request.reboot_type}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reboot instance: {e}",
        )
