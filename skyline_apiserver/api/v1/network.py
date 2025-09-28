from fastapi import APIRouter, Depends, HTTPException
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import neutron

router = APIRouter()

@router.get("/networks", response_model=schemas.NetworkList)
def list_networks(profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    try:
        session = utils.generate_session(profile)
        networks = neutron.list_networks(session=session, profile=profile)["networks"]
        return {"networks": networks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
