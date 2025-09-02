# 포트 포워딩 생성을 처리하는 API 엔드포인트를 제공하는 파일입니다.
from fastapi import APIRouter, Depends, HTTPException

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import neutron
from skyline_apiserver.schemas.portforward import PortForwardRequest, PortForwardResponse


from skyline_apiserver.client import utils
from skyline_apiserver.config import CONF


router = APIRouter()


@router.post("/portforward", response_model=PortForwardResponse, tags=["Network"])
def portforward(
    req: PortForwardRequest,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    session = utils.generate_session(profile)
    all_fips = neutron.list_floatingips(session, profile, tenant_id=profile.project.id)['floatingips']
    port_forwardings_used = 0
    for fip_item in all_fips:
        pfs = neutron.get_port_forwarding_rules(session, profile.region, fip_item['id'])
        port_forwardings_used += len(pfs)

    if port_forwardings_used >= CONF.openstack.port_forwarding_limit:
        raise HTTPException(
            status_code=400, detail="Maximum number of port forwardings for the project has been reached."
        )

    result = neutron.create_port_forwarding(req, profile)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result.get("port_forwarding")
