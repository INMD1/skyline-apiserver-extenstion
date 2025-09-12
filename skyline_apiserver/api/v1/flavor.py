from fastapi import APIRouter, Depends
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import nova
from skyline_apiserver.client import utils

router = APIRouter()

@router.get("/flavors", response_model=schemas.FlavorsResponse, summary="List Flavors")
def list_flavors(profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    flavors_from_nova = nova.list_flavors(session=session, region=profile.region)
    
    flavors = []
    for flavor in flavors_from_nova:
        extra_specs = flavor.get_keys()
        flavors.append(
            schemas.Flavor(
                id=flavor.id,
                name=flavor.name,
                vcpus=flavor.vcpus,
                ram=flavor.ram,
                disk=flavor.disk,
                is_public=getattr(flavor, 'os-flavor-access:is_public', True),
                extra_specs=extra_specs,
            )
        )
    return schemas.FlavorsResponse(flavors=flavors)

@router.get("/flavors/{flavor_id}", response_model=schemas.Flavor, summary="Get a Flavor")
def get_flavor(flavor_id: str, profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    flavor = nova.get_flavor(session=session, region=profile.region, flavor_id=flavor_id)
    extra_specs = flavor.get_keys()
    return schemas.Flavor(
        id=flavor.id,
        name=flavor.name,
        vcpus=flavor.vcpus,
        ram=flavor.ram,
        disk=flavor.disk,
        is_public=getattr(flavor, 'os-flavor-access:is_public', True),
        extra_specs=extra_specs,
    )
