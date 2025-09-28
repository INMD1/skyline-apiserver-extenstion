# 인스턴스 생성 및 포트 포워딩과 같은 네트워크 관련 작업을 처리하는 API 엔드포인트를 제공하는 파일입니다.
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import nova, neutron, cinder
import random
import time
import uuid

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


class PortForwardingDelete(BaseModel):
    floating_ip_id: str
    pf_id: str


router = APIRouter()


from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

def setup_instance_networking(server_id: str, profile: schemas.Profile, additional_ports: Optional[List[PortForwardingRule]]):
    session = utils.generate_session(profile)
    try:
        internal_ip = nova.get_server_internal_ip(session, profile, server_id)
        ssh_fip = neutron.find_floating_ip_for_ssh(session, profile.region)
        ssh_fip_id = ssh_fip["id"]

        neutron.create_port_forwarding_rule(
            session=session,
            region=profile.region,
            floatingip_id=ssh_fip_id,
            internal_ip_address=internal_ip,
            internal_port=22,
            external_port=random.randrange(1,600),
        )

        if additional_ports:
            fip = neutron.find_available_floating_ip(session, profile.region)
            fip_id = fip["id"]
            for port in additional_ports:
                neutron.create_port_forwarding_rule(
                    session=session,
                    region=profile.region,
                    floatingip_id=fip_id,
                    internal_ip_address=internal_ip,
                    internal_port=port.internal_port,
                    external_port=port.external_port,
                    protocol=port.protocol,
                )
    except Exception as e:
        # You might want to log this error or update the server status to ERROR
        print(f"Failed to setup networking for server {server_id}: {e}")

@router.post("/instances", status_code=status.HTTP_202_ACCEPTED)
def create_instance(
    instance: InstanceCreate,
    background_tasks: BackgroundTasks,
    profile: schemas.Profile = Depends(deps.get_profile_from_header)
):
    session = utils.generate_session(profile)

    # 인스턴스 요청을 DB 같은 데 먼저 기록 (id 미리 생성)
    request_id = str(uuid.uuid4())
    print(f"[REQUEST] Received create request {request_id} for instance {instance}")

    # 실제 생성 로직은 백그라운드 태스크로 돌림
    background_tasks.add_task(
        _provision_instance,
        session,
        profile,
        instance,
        request_id
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
            for _ in range(60):
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
            print(f"[{request_id}] Created instance {server.id} from volume {volume.id}")
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
            print(f"[{request_id}] Created instance {server.id}")

        # 추가 네트워크 세팅도 백그라운드로
        setup_instance_networking(server.id, profile, instance.additional_ports)

        # 성공 기록 (DB 업데이트 같은 것)
        print(f"[{request_id}] Instance {server.id} provisioning completed")

    except Exception as e:
        print(f"[{request_id}] Failed: {e}")



from skyline_apiserver.config import CONF


@router.get("/instances/{instance_id}", response_model=schemas.Instance)
def get_instance(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    try:
        server = nova.get_server(session, profile, instance_id)
        return server
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/port_forwardings")
def add_port_forwarding(pf_request: PortForwardingAdd, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    try:
        all_fips = neutron.list_floatingips(session, profile, tenant_id=profile.project.id)['floatingips']
        port_forwardings_used = 0
        for fip_item in all_fips:
            pfs = neutron.get_port_forwarding_rules(session, profile.region, fip_item['id'])
            port_forwardings_used += len(pfs)

        if port_forwardings_used >= CONF.openstack.port_forwarding_limit:
            raise HTTPException(
                status_code=400, detail="Maximum number of port forwardings for the project has been reached."
            )

        fip = neutron.find_available_floating_ip(session, profile.region)
        fip_id = fip["id"]

        pf = neutron.create_port_forwarding_rule(
            session=session,
            region=profile.region,
            floatingip_id=fip_id,
            internal_ip_address=pf_request.internal_ip,
            internal_port=pf_request.internal_port,
            external_port=pf_request.external_port,  # Can be None
            protocol=pf_request.protocol,
        )
        return {"message": "Port forwarding created successfully", "port_forwarding": pf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create port forwarding: {e}")


@router.delete("/port_forwardings", status_code=status.HTTP_204_NO_CONTENT)
def delete_port_forwarding(pf_delete: PortForwardingDelete, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
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
        raise HTTPException(status_code=500, detail=f"Failed to delete port forwarding: {e}")

class ConsoleRequest(BaseModel):
    console_type: str

@router.post("/instances/{instance_id}/console", response_model=schemas.Console)
def get_instance_console(
    instance_id: str,
    console_request: ConsoleRequest,
    profile: schemas.Profile = Depends(deps.get_profile_from_header)
):
    session = utils.generate_session(profile)
    try:
        console_data = nova.get_console_url(session, profile, instance_id, console_request.console_type)
        return schemas.Console(**console_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
