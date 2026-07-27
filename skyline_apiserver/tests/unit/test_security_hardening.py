# Copyright 2026 INMD1
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
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from starlette.responses import Response

from skyline_apiserver.api.v1 import portforward, setting, user
from skyline_apiserver.client.openstack import keystone
from skyline_apiserver.config import CONF
from skyline_apiserver.core.security import parse_access_token, set_session_cookies
from skyline_apiserver.types import constants
from skyline_apiserver.utils import roles


def _profile(*, user_id: str = "tenant-user", project_id: str = "tenant-project"):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        project=SimpleNamespace(id=project_id),
        roles=[SimpleNamespace(name="admin")],
    )


def test_session_cookie_keeps_security_attributes():
    response = Response()

    set_session_cookies(response, "signed-token", int(time.time()) + 300)

    cookies = response.headers.getlist("set-cookie")
    session_cookie = next(
        value for value in cookies if value.startswith(f"{CONF.default.session_name}=")
    )
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=strict" in session_cookie


def test_access_token_requires_all_security_claims():
    token = jwt.encode(
        {
            "keystone_token": "keystone-token",
            "region": "RegionOne",
            "exp": int(time.time()) + 300,
        },
        CONF.default.secret_key,
        algorithm=constants.ALGORITHM,
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        parse_access_token(token)


def test_hidden_setting_value_is_never_returned():
    assert setting._setting_response_value("smtp_password", "super-secret") == "********"
    assert setting._setting_response_value("smtp_host", "smtp.example.com") == (
        "smtp.example.com"
    )


def test_project_admin_is_not_automatically_platform_admin():
    assert roles.is_system_admin(_profile(user_id="unconfigured-project-admin")) is False


def test_rule_without_verifiable_owner_is_denied(monkeypatch):
    profile = _profile()
    monkeypatch.setattr(portforward, "is_system_admin", lambda unused_profile: False)

    with pytest.raises(HTTPException) as exc:
        portforward._assert_rule_access(profile, {})

    assert exc.value.status_code == 403


def test_foreign_vm_is_denied_before_portforward_call(monkeypatch):
    profile = _profile()
    foreign_server = SimpleNamespace(
        id="foreign-vm",
        tenant_id="foreign-project",
        addresses={},
    )
    monkeypatch.setattr(portforward.utils, "generate_session", lambda unused_profile: object())
    monkeypatch.setattr(
        portforward.nova,
        "get_server",
        lambda session, request_profile, vm_id: foreign_server,
    )
    monkeypatch.setattr(portforward, "is_system_admin", lambda unused_profile: False)

    with pytest.raises(HTTPException) as exc:
        portforward._get_owned_server(profile, foreign_server.id)

    assert exc.value.status_code == 403


def test_public_signup_is_disabled_by_default():
    assert CONF.default.signup_enabled is False


def test_internal_signup_requires_matching_token(monkeypatch):
    config = SimpleNamespace(
        default=SimpleNamespace(signup_enabled=False, signup_token="expected-token")
    )
    monkeypatch.setattr(user, "CONF", config)

    assert user._is_signup_authorized(None) is False
    assert user._is_signup_authorized("wrong-token") is False
    assert user._is_signup_authorized("expected-token") is True


def test_keystone_url_does_not_create_redirecting_double_slash(monkeypatch):
    config = SimpleNamespace(
        openstack=SimpleNamespace(keystone_url="http://keystone.example/v3/")
    )
    monkeypatch.setattr(keystone, "CONF", config)

    assert keystone._get_keystone_url() == "http://keystone.example/v3"
