# Copyright 2025 INMD1
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
