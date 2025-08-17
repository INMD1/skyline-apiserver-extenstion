from fastapi import APIRouter, HTTPException
from skyline_apiserver.schemas.portforward import PortForwardRequest
from skyline_apiserver.client.openstack.neutron import create_port_forwarding

router = APIRouter()

@router.post("/portforward", tags=["Network"])
async def portforward(req: PortForwardRequest):
    result = await create_port_forwarding(req)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Port forwarding created"}