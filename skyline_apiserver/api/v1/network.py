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
