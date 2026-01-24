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

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from skyline_apiserver.api import deps
from skyline_apiserver.client.openstack import activity as activity_client
from skyline_apiserver.schemas.activity import Activity
from skyline_apiserver import schemas

router = APIRouter()


@router.get(
    "/activities",
    response_model=List[Activity],
    status_code=status.HTTP_200_OK,
    description="List activities for current user",
)
def list_activities(
    profile: schemas.Profile = Depends(deps.get_profile),
):
    return activity_client.get_activities_by_user(profile.user.id)
