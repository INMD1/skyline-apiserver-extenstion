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
from fastapi import APIRouter, Depends, HTTPException, Header, status
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils, portforward_client
from skyline_apiserver.client.openstack import nova, cinder, neutron
from typing import Optional
from skyline_apiserver.types import constants
from skyline_apiserver.config import CONF

router = APIRouter()


@router.get("/limits", response_model=schemas.LimitSummary)
async def get_limit_summary(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
):

    session = utils.generate_session(profile)
    try:
        nova_quotas = nova.get_quotas(session, profile, global_request_id=x_openstack_request_id)
        cinder_quotas = cinder.get_quotas(session, profile, global_request_id=x_openstack_request_id)
        neutron_quotas = neutron.get_quotas(session, profile, global_request_id=x_openstack_request_id)

        nova_servers = nova.list_servers(profile, session, global_request_id=x_openstack_request_id)
        instances_used = len(nova_servers)
        cores_used = sum(s.flavor['vcpus'] for s in nova_servers)
        ram_used = sum(s.flavor['ram'] for s in nova_servers)

        cinder_volumes = cinder.list_volumes(profile, session, global_request_id=x_openstack_request_id)
        volumes_used = len(cinder_volumes)
        gigabytes_used = sum(v.size for v in cinder_volumes)
        cinder_snapshots = cinder.list_volume_snapshots(profile, session, global_request_id=x_openstack_request_id)
        snapshots_used = len(cinder_snapshots)

        neutron_floatingips = neutron.list_floatingips(session, profile, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        floatingips_used = len(neutron_floatingips['floatingips'])

        # 포트포워딩 사용량: 외부 Proxy API에서 현재 프로젝트 VM 기준으로 집계
        port_forwardings_used = 0
        try:
            vm_ids = [s.id for s in nova_servers]
            for vm_id in vm_ids:
                rules = await portforward_client.get_portforwardings_by_vm(vm_id)
                port_forwardings_used += len(rules)
        except Exception:
            # 외부 API 오류 시 0으로 표시 (limits 전체를 실패시키지 않음)
            port_forwardings_used = 0

        neutron_networks = neutron.list_networks(session, profile, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        networks_used = len(neutron_networks['networks'])
        neutron_ports = neutron.list_ports(session, profile.region, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        ports_used = len(list(neutron_ports))
        neutron_routers = neutron.list_routers(session, profile, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        routers_used = len(neutron_routers['routers'])
        neutron_subnets = neutron.list_subnets(session, profile, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        subnets_used = len(neutron_subnets['subnets'])
        neutron_security_groups = neutron.list_security_groups(session, profile, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
        security_groups_used = len(neutron_security_groups['security_groups'])

        quotas = {
            "instances": {"in_use": instances_used, "limit": getattr(nova_quotas, 'instances', -1)},
            "cores": {"in_use": cores_used, "limit": getattr(nova_quotas, 'cores', -1)},
            "ram": {"in_use": ram_used, "limit": getattr(nova_quotas, 'ram', -1)},
            "volumes": {"in_use": volumes_used, "limit": getattr(cinder_quotas, 'volumes', -1)},
            "snapshots": {"in_use": snapshots_used, "limit": getattr(cinder_quotas, 'snapshots', -1)},
            "gigabytes": {"in_use": gigabytes_used, "limit": getattr(cinder_quotas, 'gigabytes', -1)},
            "floatingip": {"in_use": floatingips_used, "limit": neutron_quotas.get('floatingip', -1)},
            "port_forwardings": {"in_use": port_forwardings_used, "limit": CONF.openstack.port_forwarding_limit},
            "network": {"in_use": networks_used, "limit": neutron_quotas.get('network', -1)},
            "port": {"in_use": ports_used, "limit": neutron_quotas.get('port', -1)},
            "router": {"in_use": routers_used, "limit": neutron_quotas.get('router', -1)},
            "subnet": {"in_use": subnets_used, "limit": neutron_quotas.get('subnet', -1)},
            "security_group": {"in_use": security_groups_used, "limit": neutron_quotas.get('security_group', -1)},
            "security_group_rule": {"in_use": -1, "limit": neutron_quotas.get('security_group_rule', -1)},
        }
        return schemas.LimitSummary(quotas=quotas)

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
