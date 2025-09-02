# Copyright 2021 99cloud
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

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table

METADATA = MetaData()


RevokedToken = Table(
    "revoked_token",
    METADATA,
    Column("uuid", String(length=128), nullable=False, index=True, unique=False),
    Column("expire", Integer, nullable=False),
)

Settings = Table(
    "settings",
    METADATA,
    Column("key", String(length=128), nullable=False, index=True, unique=True),
    Column("value", JSON, nullable=True),
)

UserDetails = Table(
    "user_details",
    METADATA,
    Column("user_id", String(length=64), primary_key=True, nullable=False),
    # DB쿼리가 바뀌만 이쪽도 수정해주세요.
    Column("student_id", String(length=255), nullable=True),
)
