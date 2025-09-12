from fastapi import APIRouter, Depends, status
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import nova
from skyline_apiserver.client import utils

router = APIRouter()

@router.get("/keypairs", response_model=schemas.KeypairsResponse, summary="List Keypairs")
def list_keypairs(profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    keypairs_from_nova = nova.list_keypairs(session=session, region=profile.region)
    
    keypairs = [schemas.Keypair.model_validate(kp.to_dict()['keypair']) for kp in keypairs_from_nova]
    return schemas.KeypairsResponse(keypairs=keypairs)

@router.get("/keypairs/{keypair_name}", response_model=schemas.Keypair, summary="Get a Keypair")
def get_keypair(keypair_name: str, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    keypair = nova.get_keypair(session=session, region=profile.region, keypair_name=keypair_name)
    return schemas.Keypair.model_validate(keypair.to_dict()['keypair'])

@router.post("/keypairs", response_model=schemas.KeypairDetail, status_code=status.HTTP_201_CREATED, summary="Create a Keypair")
def create_keypair(keypair_in: schemas.KeypairCreate, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    keypair = nova.create_keypair(
        session=session, 
        region=profile.region, 
        name=keypair_in.name, 
        public_key=keypair_in.public_key
    )
    return schemas.KeypairDetail.model_validate(keypair.to_dict()['keypair'])

@router.delete("/keypairs/{keypair_name}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a Keypair")
def delete_keypair(keypair_name: str, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    nova.delete_keypair(session=session, region=profile.region, keypair_name=keypair_name)
    return
