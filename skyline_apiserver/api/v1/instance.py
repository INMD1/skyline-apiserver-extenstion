# 인스턴스 생성 및 포트 포워딩과 같은 네트워크 관련 작업을 처리하는 API 엔드포인트를 제공하는 파일입니다.
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import nova, neutron


class InstanceCreate(BaseModel):
    image_id: str
    flavor_id: str
    key_name: str
    network_id: str


class PortForwardingAdd(BaseModel):
    internal_ip: str
    internal_port: int
    external_port: int | None = None
    protocol: str = "tcp"


class PortForwardingDelete(BaseModel):
    floating_ip_id: str
    pf_id: str


router = APIRouter()


@router.post("/instances", status_code=status.HTTP_201_CREATED)
def create_instance(instance: InstanceCreate, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    try:
        session = utils.generate_session(profile)
        server = nova.create_instance_with_network(
            session=session,
            profile=profile,
            name=f"{profile.user.name}-vm",
            image_id=instance.image_id,
            flavor_id=instance.flavor_id,
            net_id=instance.network_id,
            key_name=instance.key_name,
        )

        internal_ip = nova.get_server_internal_ip(session, profile, server.id)
        fip = neutron.find_floating_ip_for_ssh(session, profile.region)
        fip_id = fip["id"]

        pf = neutron.create_port_forwarding_rule(
            session=session,
            region=profile.region,
            floatingip_id=fip_id,
            internal_ip_address=internal_ip,
            internal_port=22,
            external_port=22, 
        )

        # The original code had a security group rule creation.
        # This needs more details like which security group to use.
        # For now, skipping this part.

        return {
            "vm_id": server.id,
            "ssh": f"ssh <user>@{fip['floating_ip_address']} -p {pf['external_port']}",
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


from skyline_apiserver.config import CONF


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
