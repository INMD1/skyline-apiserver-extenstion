# API를 통해 동적으로 관리될 수 있는 설정 항목들을 정의하는 파일입니다.
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

from typing import Any, Dict, List, Optional

from pydantic.types import StrictBool, StrictInt, StrictStr

from skyline_apiserver.config.base import Opt

base_settings = Opt(
    name="base_settings",
    description="base settings list",
    schema=List[StrictStr],
    default=[
        "flavor_families",
        "gpu_models",
        "usb_models",
        "instance_lifecycle_enabled",
        "instance_lifetime_days",
        "instance_reply_deadline_days",
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "smtp_use_tls",
        "smtp_from_address",
    ],
)

flavor_families = Opt(
    name="flavor_families",
    description="Flavor families",
    schema=List[Dict[str, Any]],
    default=[
        {
            "architecture": "x86_architecture",
            "categories": [
                {"name": "general_purpose", "properties": []},
                {"name": "compute_optimized", "properties": []},
                {"name": "memory_optimized", "properties": []},
                # {"name": "big_data", "properties": []},
                # {"name": "local_ssd", "properties": []},
                {"name": "high_clock_speed", "properties": []},
            ],
        },
        {
            "architecture": "heterogeneous_computing",
            "categories": [
                {"name": "compute_optimized_type_with_gpu", "properties": []},
                {"name": "visualization_compute_optimized_type_with_gpu", "properties": []},
                # {"name": "compute_optimized_type", "properties": []},
            ],
        },
        # {
        #     "architecture": "arm_architecture",
        #     "categories": [
        #         {"name": "general_purpose", "properties": []},
        #         {"name": "compute_optimized", "properties": []},
        #         {"name": "memory_optimized", "properties": []},
        #         {"name": "big_data", "properties": []},
        #         {"name": "local_ssd", "properties": []},
        #         {"name": "high_clock_speed", "properties": []},
        #     ],
        # },
    ],
)

gpu_models = Opt(
    name="gpu_models",
    description="gpu_models",
    schema=List[StrictStr],
    default=["nvidia_t4"],
)

usb_models = Opt(
    name="usb_models",
    description="usb_models",
    schema=List[StrictStr],
    default=["usb_c"],
)


# ──────────────────────────────────────────────
#  인스턴스 라이프사이클 이메일 알림 설정
# ──────────────────────────────────────────────

instance_lifecycle_enabled = Opt(
    name="instance_lifecycle_enabled",
    description="인스턴스 수명 관리 기능을 활성화합니다. True 이면 만료 전 이메일을 보내고, 회신이 없으면 자동 삭제합니다.",
    schema=StrictBool,
    default=False,
)

instance_lifetime_days = Opt(
    name="instance_lifetime_days",
    description="인스턴스 최대 운영 기간(일). 이 기간이 지나면 이메일 알림을 발송합니다.",
    schema=StrictInt,
    default=30,
)

instance_reply_deadline_days = Opt(
    name="instance_reply_deadline_days",
    description="이메일 발송 후 사용자가 연장 버튼을 눌러야 하는 기한(일). 이 기간 내 응답 없으면 자동 삭제합니다.",
    schema=StrictInt,
    default=7,
)

smtp_host = Opt(
    name="smtp_host",
    description="이메일 발송에 사용할 SMTP 서버 호스트",
    schema=StrictStr,
    default="",
)

smtp_port = Opt(
    name="smtp_port",
    description="SMTP 서버 포트 (TLS: 587, SSL: 465, 일반: 25)",
    schema=StrictInt,
    default=587,
)

smtp_user = Opt(
    name="smtp_user",
    description="SMTP 인증 사용자명",
    schema=StrictStr,
    default="",
)

smtp_password = Opt(
    name="smtp_password",
    description="SMTP 인증 비밀번호",
    schema=StrictStr,
    default="",
)

smtp_use_tls = Opt(
    name="smtp_use_tls",
    description="SMTP STARTTLS 사용 여부",
    schema=StrictBool,
    default=True,
)

smtp_from_address = Opt(
    name="smtp_from_address",
    description="발신자 이메일 주소",
    schema=StrictStr,
    default="",
)


GROUP_NAME = __name__.split(".")[-1]
ALL_OPTS = (
    base_settings,
    flavor_families,
    gpu_models,
    usb_models,
    instance_lifecycle_enabled,
    instance_lifetime_days,
    instance_reply_deadline_days,
    smtp_host,
    smtp_port,
    smtp_user,
    smtp_password,
    smtp_use_tls,
    smtp_from_address,
)

__all__ = ("GROUP_NAME", "ALL_OPTS")
