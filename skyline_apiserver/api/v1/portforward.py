from fastapi import APIRouter, HTTPException
from schemas.portforward import PortForwardRequest
from client.openstack.neutron import create_port_forwarding

router = APIRouter()

@router.post("/portforward", tags=["Network"])
async def portforward(req: PortForwardRequest):
    result = await create_port_forwarding(req)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Port forwarding created"}