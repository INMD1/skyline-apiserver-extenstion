경고
====

.. warning::

   본 API 서버는 **Skyline** 에서 추가적으로 기능이 확장된 버전입니다.  
   아직 개발 중이므로 버그가 발생할 수 있습니다.

Skyline 소개
============

**Skyline** 은 OpenStack 대시보드로, UI/UX가 최적화되어 있으며 OpenStack **Train** 버전 이상을 지원합니다.  
현대적인 기술 스택과 생태계를 기반으로 하여, 개발자가 더 쉽게 유지관리할 수 있고,  
사용자 입장에서도 더 뛰어난 성능과 높은 동시성 처리 능력을 제공합니다.

Skyline의 마스코트는 **구색 사슴(아홉 가지 색의 사슴)** 입니다.  
이 사슴은 둔황 벽화 *구색왕록* 에서 유래한 것으로, **인과응보와 감사** 의 의미를 지니고 있습니다.  
이는 Skyline의 주체인 **99cloud** 가 커뮤니티를 포용하고 환원해 온 철학과도 맞닿아 있습니다.  

Skyline 또한 이 구색 사슴처럼 가볍고, 우아하며, 강력한 오픈스택 대시보드가 되기를 바랍니다.

추가/확장된 API 목록
====================

회원 관리 관련
--------------

- ``/api/v1/login`` : 로그인 및 사용자 프로필 가져오기
- ``/api/v1/sso`` : SSO 설정 조회
- ``/api/v1/websso`` : WebSSO 인증 요청
- ``/api/v1/profile`` : 사용자 프로필 조회
- ``/api/v1/logout`` : 로그아웃
- ``/api/v1/signup`` : 사용자 회원가입

서버 관리 관련
--------------

- ``/api/v1/extension/servers`` : 서버 목록 조회
- ``/api/v1/extension/volumes`` : 볼륨 목록 조회
- ``/api/v1/extension/volume_snapshots`` : 볼륨 스냅샷 목록 조회
- ``/api/v1/extension/ports`` : 네트워크 포트 목록 조회
- ``/api/v1/extension/compute-services`` : 컴퓨트 서비스 목록 조회
- ``/api/v1/query`` : Prometheus 단일 쿼리 API
- ``/api/v1/query_range`` : Prometheus 범위 쿼리 API
- ``/api/v1/contrib/keystone_endpoints`` : Keystone 엔드포인트 목록 조회
- ``/api/v1/policies/check`` : 정책 권한 확인
- ``/api/v1/setting/{key}`` : 특정 설정 항목 조회 또는 초기화
- ``/api/v1/setting`` : 설정 항목 수정
- ``/api/v1/settings`` : 모든 설정 목록 조회
- ``/api/v1/portforward`` : 포트포워딩 생성
- ``/api/v1/instances`` : 인스턴스 생성
- ``/api/v1/port_forwardings`` : 포트포워딩 추가 또는 삭제
- ``/api/v1/instances/{instance_id}/console`` : 인스턴스 콘솔 정보 가져오기
- ``/api/v1/limits`` : 리소스 한도 요약 조회
- ``/api/v1/instances/{instance_id}/performance`` : 인스턴스 성능 데이터 조회
