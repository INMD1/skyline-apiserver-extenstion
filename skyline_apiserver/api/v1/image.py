from fastapi import APIRouter, Depends
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import glance
from skyline_apiserver.client import utils

router = APIRouter()

@router.get("/images", response_model=schemas.ImagesResponse, summary="List Images")
def list_images(profile: schemas.Profile = Depends(deps.get_profile_from_header)):
    session = utils.generate_session(profile)
    images_from_glance = glance.list_images(profile, session, global_request_id=None)
    
    images = []
    for image in images_from_glance:
        images.append(
            schemas.Image(
                id=image.id,
                name=image.name,
                status=image.status,
                visibility=image.visibility,
                size=image.size,
                disk_format=image.disk_format,
                owner=image.owner,
                created_at=image.created_at,
                updated_at=image.updated_at,
                tags=image.tags,
                min_disk=image.min_disk,
                min_ram=image.min_ram,
                protected=image.protected,
            )
        )
    return schemas.ImagesResponse(images=images)
