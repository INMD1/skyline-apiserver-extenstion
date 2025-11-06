# 사용자가 활동한 기록을 저장합니다.
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

from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session
from skyline_apiserver.db import api as db_api

def write_db_backed_token(
 session: Session,
 message: str,
 status: str #success or failure 2개로 구분됨
) -> Any:
 