from fastapi import APIRouter, Depends, Query, HTTPException, status
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.utils.httpclient import _http_request
from skyline_apiserver.config import CONF
from skyline_apiserver.types import constants

router = APIRouter()

def query_prometheus(query: str, profile: schemas.Profile):
    # Simplified version of prometheus_query from prometheus.py
    params = {'query': query}
    auth = None
    if CONF.default.prometheus_enable_basic_auth:
        auth = (
            CONF.default.prometheus_basic_auth_user,
            CONF.default.prometheus_basic_auth_password,
        )
    resp = _http_request(
        url=CONF.default.prometheus_endpoint + constants.PROMETHEUS_QUERY_API,
        params=params,
        auth=auth,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    json_resp = resp.json()
    # filter by project_id
    if 'data' in json_resp and 'result' in json_resp['data']:
        result = [
            i
            for i in json_resp['data']['result']
            if "project_id" in i.get('metric', {}) and i['metric']["project_id"] == profile.project.id
        ]
        json_resp['data']['result'] = result
    return json_resp['data']['result']


@router.get("/instances/{instance_id}/performance", response_model=schemas.PerformanceData)
def get_instance_performance(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header)
):
    queries = {
        "cpu_usage": f'instance:node_cpu_utilisation:rate5m{{instance_id="{instance_id}"}}',
        "memory_usage": f'instance:node_memory_utilisation:ratio{{instance_id="{instance_id}"}}',
        "disk_read_bytes": f'instance:node_disk_read_bytes_total:rate5m{{instance_id="{instance_id}"}}',
        "disk_write_bytes": f'instance:node_disk_write_bytes_total:rate5m{{instance_id="{instance_id}"}}',
        "network_incoming_bytes": f'instance:node_network_receive_bytes_total:rate5m{{instance_id="{instance_id}"}}',
        "network_outgoing_bytes": f'instance:node_network_transmit_bytes_total:rate5m{{instance_id="{instance_id}"}}',
    }

    performance_data = {}
    for key, query in queries.items():
        performance_data[key] = query_prometheus(query, profile)

    return schemas.PerformanceData(**performance_data)
