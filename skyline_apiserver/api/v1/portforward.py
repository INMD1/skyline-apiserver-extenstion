from fastapi import APIRouter, HTTPException
from skyline_apiserver.schemas.portforward import PortForwardRequest
from skyline_apiserver.client.openstack.neutron import create_port_forwarding

router = APIRouter()


@router.post("/portforward", response_model=PortForwardResponse, tags=["Network"])
async def portforward(
    req: PortForwardRequest,
    profile: schemas.Profile = Depends(deps.get_profile_update_jwt),
):
    result = await neutron.create_port_forwarding(req, profile)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result["port_forwarding"]
