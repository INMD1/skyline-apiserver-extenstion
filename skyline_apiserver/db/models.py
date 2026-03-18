# 애플리케이션의 데이터베이스 스키마(테이블)를 SQLAlchemy 모델로 정의하는 파일입니다.
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

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, DateTime

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


UserActivity = Table(
    "user_activity",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(length=64), nullable=False),
    Column("project_id", String(length=64), nullable=False),
    Column("category", String(length=128), nullable=False),
    Column("message", String(length=512), nullable=False),
    Column("status", String(length=32), nullable=False),  # 'success' or
    Column("token", String(length=256), nullable=False),
    Column("timestamp", Integer, nullable=False),
    Column("created_at", DateTime, nullable=True),
)
