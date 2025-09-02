from fastapi import APIRouter, Depends, HTTPException

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import neutron
from skyline_apiserver.schemas.portforward import PortForwardRequest, PortForwardResponse


router = APIRouter()


@router.post("/portforward", response_model=PortForwardResponse, tags=["Network"])
def portforward(
    req: PortForwardRequest,
    profile: schemas.Profile = Depends(deps.get_profile_update_jwt),
):
    result = neutron.create_port_forwarding(req, profile)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result.get("port_forwarding")
