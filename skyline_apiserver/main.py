# FastAPI 애플리케이션의 메인 파일입니다. 앱 설정, 생명주기 이벤트, 미들웨어, API 라우터 포함 등을 처리합니다.
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

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import jose
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from skyline_apiserver.api.v1 import api_router
from skyline_apiserver.config import CONF, configure
from skyline_apiserver.context import RequestContext
from skyline_apiserver.core.security import (
    generate_profile,
    generate_profile_by_token,
    parse_access_token,
)
from skyline_apiserver.db import api as db_api, setup as db_setup
from skyline_apiserver.log import LOG, setup as log_setup
from skyline_apiserver.policy import setup as policies_setup
from skyline_apiserver.types import constants

PROJECT_NAME = "Skyline API"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure("skyline")
    log_setup(
        Path(CONF.default.log_dir).joinpath(CONF.default.log_file),
        debug=CONF.default.debug,
    )
    policies_setup()
    db_setup()

    # Set all CORS enabled origins
    if CONF.default.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in CONF.default.cors_allow_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    LOG.debug("Skyline API server start")
    yield
    LOG.debug("Skyline API server stop")


app = FastAPI(
    title=PROJECT_NAME,
    openapi_url=f"{constants.API_PREFIX}/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def validate_token(request: Request, call_next):
    url_path = request.url.path
    LOG.debug(f"Request path: {url_path}")

    # Skip authentication for login and static endpoints
    ignore_urls = [
        f"{constants.API_PREFIX}/login",
        f"{constants.API_PREFIX}/logout",
        f"{constants.API_PREFIX}/signup",
        f"{constants.API_PREFIX}/websso",
        "/static",
        "/docs",
        f"{constants.API_PREFIX}/openapi.json",
        "/favicon.ico",
        f"{constants.API_PREFIX}/sso",
        f"{constants.API_PREFIX}/contrib/keystone_endpoints",
        # f"{constants.API_PREFIX}/contrib/domains",
        f"{constants.API_PREFIX}/contrib/regions",
        f"{constants.API_PREFIX}/limits",
    ]

    for ignore_url in ignore_urls:
        if url_path.startswith(ignore_url):
            return await call_next(request)

    response = await call_next(request)

    # Handle token renewal in response
    if hasattr(request.state, "token_needs_renewal") and request.state.token_needs_renewal:
        response.set_cookie(CONF.default.session_name, request.state.new_token)
        response.set_cookie(constants.TIME_EXPIRED_KEY, request.state.new_exp)

    return response


app.include_router(api_router, prefix=constants.API_PREFIX)
