from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import nova, cinder, neutron
from typing import Optional
from skyline_apiserver.types import constants
from skyline_apiserver.config import CONF

router = APIRouter()


@router.get("/limits", response_model=schemas.LimitSummary)
def get_limit_summary(
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
        port_forwardings_used = 0
        for fip in neutron_floatingips['floatingips']:
            pfs = neutron.get_port_forwarding_rules(session, profile.region, fip['id'])
            port_forwardings_used += len(pfs)

        neutron_networks = neutron.list_networks(profile, session, global_request_id=x_openstack_request_id, tenant_id=profile.project.id)
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
            "security_group_rule": {"in_use": -1, "limit": neutron_quotas.get('security_group_rule', -1)}, # security_group_rule usage is not easy to calculate
        }
        return schemas.LimitSummary(quotas=quotas)

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
