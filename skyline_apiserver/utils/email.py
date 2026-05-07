# 인스턴스 라이프사이클 이메일 알림을 발송하는 유틸리티 모듈입니다.
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from skyline_apiserver.log import LOG


def _get_smtp_config() -> dict[str, Any]:
    """DB 또는 config에서 현재 SMTP 설정을 읽어 반환합니다."""
    from skyline_apiserver.config import CONF
    from skyline_apiserver.db import api as db_api

    keys = [
        "smtp_host", "smtp_port", "smtp_user",
        "smtp_password", "smtp_use_tls", "smtp_from_address",
    ]
    cfg: dict[str, Any] = {}
    for key in keys:
        db_val = db_api.get_setting(key)
        cfg[key] = db_val.value if db_val else getattr(CONF.setting, key)
    return cfg


def send_lifecycle_warning_email(
    to_email: str,
    instance_id: str,
    instance_name: str,
    expires_at_str: str,
    extend_url: str,
) -> bool:
    """인스턴스 만료 경고 이메일을 발송합니다.

    Returns:
        True  - 발송 성공
        False - 발송 실패 (설정 누락 또는 SMTP 오류)
    """
    cfg = _get_smtp_config()

    if not cfg["smtp_host"] or not cfg["smtp_from_address"]:
        LOG.warning("SMTP 설정이 완료되지 않아 이메일을 발송할 수 없습니다.")
        return False

    subject = f"[클라우드 플랫폼] 인스턴스 '{instance_name}' 만료 예정 안내"

    html_body = f"""
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <h2 style="color:#1a73e8;">인스턴스 만료 예정 안내</h2>
  <p>안녕하세요,</p>
  <p>
    아래 인스턴스가 <strong>{expires_at_str}</strong>에 만료될 예정입니다.<br>
    계속 사용하시려면 아래 <strong>연장하기</strong> 버튼을 눌러 주세요.
  </p>
  <table style="border-collapse:collapse; width:100%; margin:16px 0;">
    <tr>
      <td style="padding:8px; background:#f5f5f5; font-weight:bold; width:140px;">인스턴스 이름</td>
      <td style="padding:8px;">{instance_name}</td>
    </tr>
    <tr>
      <td style="padding:8px; background:#f5f5f5; font-weight:bold;">인스턴스 ID</td>
      <td style="padding:8px;">{instance_id}</td>
    </tr>
    <tr>
      <td style="padding:8px; background:#f5f5f5; font-weight:bold;">만료 예정일</td>
      <td style="padding:8px; color:#d32f2f; font-weight:bold;">{expires_at_str}</td>
    </tr>
  </table>
  <p>
    <a href="{extend_url}"
       style="display:inline-block; padding:12px 24px; background:#1a73e8;
              color:#fff; border-radius:4px; text-decoration:none; font-size:15px;">
      연장하기 (1개월 연장)
    </a>
  </p>
  <hr style="margin:24px 0; border:none; border-top:1px solid #eee;">
  <p style="font-size:12px; color:#999;">
    기한 내 응답이 없으면 인스턴스가 자동으로 삭제됩니다.<br>
    이 메일은 자동 발송되었습니다. 문의는 관리자에게 연락해 주세요.
  </p>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["smtp_from_address"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["smtp_use_tls"]:
            server = smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=10)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=10)

        if cfg["smtp_user"] and cfg["smtp_password"]:
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(cfg["smtp_from_address"], [to_email], msg.as_string())
        server.quit()
        LOG.info(f"라이프사이클 경고 이메일 발송 완료: {to_email} / instance={instance_id}")
        return True
    except Exception as exc:
        LOG.error(f"이메일 발송 실패: {exc}")
        return False
