# 인스턴스 라이프사이클 주기적 검사 스케줄러입니다.
# - 매 시간마다 실행되어 만료 임박 인스턴스에 이메일을 발송하고
#   회신 없는 인스턴스를 자동 삭제합니다.
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from skyline_apiserver.log import LOG


def _get_lifecycle_settings() -> dict:
    """현재 라이프사이클 설정값(DB 우선, 없으면 CONF)을 반환합니다."""
    from skyline_apiserver.config import CONF
    from skyline_apiserver.db import api as db_api

    def _val(key: str):
        row = db_api.get_setting(key)
        return row.value if row else getattr(CONF.setting, key)

    return {
        "enabled": _val("instance_lifecycle_enabled"),
        "lifetime_days": int(_val("instance_lifetime_days")),
        "reply_deadline_days": int(_val("instance_reply_deadline_days")),
        # admin 프로젝트 이름 (예외 처리용)
        "admin_project": CONF.openstack.system_project,
    }


def _get_admin_project_id(admin_project_name: str) -> str | None:
    """Keystone에서 admin 프로젝트의 ID를 조회합니다."""
    try:
        from keystoneauth1.identity import v3
        from keystoneauth1 import session as ks_session
        from keystoneclient.v3 import client as ks_client
        from skyline_apiserver.config import CONF

        auth = v3.Password(
            auth_url=CONF.openstack.keystone_url,
            username=CONF.openstack.system_user_name,
            password=CONF.openstack.system_user_password,
            user_domain_name=CONF.openstack.system_user_domain,
            project_name=CONF.openstack.system_project,
            project_domain_name=CONF.openstack.system_project_domain,
        )
        sess = ks_session.Session(auth=auth)
        kc = ks_client.Client(session=sess)
        for p in kc.projects.list(name=admin_project_name):
            return p.id
    except Exception as exc:
        LOG.warning(f"[Lifecycle] admin 프로젝트 ID 조회 실패: {exc}")
    return None


async def _delete_instance(instance_id: str, project_id: str) -> bool:
    """OpenStack Nova를 통해 인스턴스를 삭제합니다."""
    try:
        from skyline_apiserver.client.openstack import nova
        from skyline_apiserver.config import CONF
        from skyline_apiserver.core.security import generate_profile

        # 시스템 토큰으로 인스턴스 삭제 (관리자 권한)
        from openstack import connection as os_connection

        conn = os_connection.Connection(
            auth_url=CONF.openstack.keystone_url,
            project_name=CONF.openstack.system_project,
            username=CONF.openstack.system_user,
            password=CONF.openstack.system_user_password,
            user_domain_name=CONF.openstack.system_user_domain,
            project_domain_name=CONF.openstack.system_project_domain,
        )
        conn.compute.delete_server(instance_id, force=True)
        LOG.info(f"[Lifecycle] 인스턴스 자동 삭제 완료: {instance_id}")
        return True
    except Exception as exc:
        LOG.error(f"[Lifecycle] 인스턴스 삭제 실패 ({instance_id}): {exc}")
        return False


async def run_lifecycle_check() -> None:
    """한 번의 라이프사이클 검사 사이클을 실행합니다."""
    from skyline_apiserver.db import api as db_api
    from skyline_apiserver.utils.email import send_lifecycle_warning_email

    settings = _get_lifecycle_settings()
    if not settings["enabled"]:
        return

    now = int(time.time())
    reply_grace = settings["reply_deadline_days"] * 86400

    # admin 프로젝트 ID 조회 (예외 처리용 이중 안전장치)
    admin_project_id = _get_admin_project_id(settings["admin_project"])

    # ── 1단계: 만료 시각이 지난 인스턴스에 이메일 발송 ──────────────────────
    expiring = db_api.list_instance_lifecycles_expiring_before(now)
    for row in expiring:
        # admin 프로젝트는 예외 처리
        if admin_project_id and row.project_id == admin_project_id:
            LOG.debug(f"[Lifecycle] admin 프로젝트 인스턴스 스킵: {row.instance_id}")
            continue

        if row.email_status == "none":
            expires_str = datetime.fromtimestamp(row.expires_at, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            extend_url = f"/instances/{row.instance_id}/extend"

            sent = send_lifecycle_warning_email(
                to_email=row.user_email or "",
                instance_id=row.instance_id,
                instance_name=row.instance_name or row.instance_id,
                expires_at_str=expires_str,
                extend_url=extend_url,
            )
            if sent:
                db_api.update_instance_lifecycle_email_sent(row.instance_id, now)
                LOG.info(f"[Lifecycle] 만료 이메일 발송: instance={row.instance_id}")

    # ── 2단계: 이메일 발송 후 유예 기간이 지났는데도 연장 안 한 인스턴스 삭제 ──
    deadline = now - reply_grace
    overdue = db_api.list_instance_lifecycles_awaiting_reply(deadline)
    for row in overdue:
        # admin 프로젝트는 예외 처리
        if admin_project_id and row.project_id == admin_project_id:
            LOG.debug(f"[Lifecycle] admin 프로젝트 인스턴스 삭제 스킵: {row.instance_id}")
            continue

        LOG.warning(
            f"[Lifecycle] 자동 삭제 대상: instance={row.instance_id} "
            f"email_sent_at={row.email_sent_at}"
        )
        deleted = await _delete_instance(row.instance_id, row.project_id)
        if deleted:
            db_api.update_instance_lifecycle_deleted(row.instance_id)


async def start_lifecycle_scheduler() -> None:
    """앱 시작 시 백그라운드에서 계속 실행되는 스케줄러 코루틴입니다.

    매 1시간(3600초)마다 run_lifecycle_check()를 호출합니다.
    """
    LOG.info("[Lifecycle] 스케줄러 시작")
    while True:
        try:
            await run_lifecycle_check()
        except Exception as exc:
            LOG.error(f"[Lifecycle] 스케줄러 오류: {exc}")
        await asyncio.sleep(3600)
