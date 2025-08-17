from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from client.openstack import nova, neutron
from client.openstack.keystone import get_openstack_conn

class PortForwardingRequest(BaseModel):
    fip_id: str
    internal_ip: str
    internal_port: int
    external_port: int | None = None
    protocol: str = 'tcp'

class PortForwardingDeleteRequest(BaseModel):
    fip_id: str
    pf_id: str

router = APIRouter()


@router.post("/instance/create")
def create_instance(image_id: str, flavor_id: str, key_name: str, user_project_id: str):
    try:
        conn = get_openstack_conn(project_id=user_project_id)

        net = conn.network.find_network("공통 네트워크 이름")
        net_id = net.id if net else None
        server = nova.create_instance_with_network(conn, "user-vm", image_id, flavor_id, net_id, key_name)

        internal_ip = server.addresses[next(iter(server.addresses))][0]['addr']
        fip = neutron.find_fip_for_ssh(conn)
        fip_id = fip.id

        pf = neutron.create_port_forwarding(conn, fip_id, internal_ip, 22)

        sg = conn.network.find_security_group("default")
        neutron.create_security_group_rule(conn, sg.id, direction="ingress", remote_group_id=sg.id)

        return {
            "vm_id": server.id,
            "ssh": f"ssh ubuntu@<SSH_PUBLIC_IP> -p {pf.external_port}"
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/port-forwarding/delete")
def delete_port_forwarding(data: PortForwardingDeleteRequest, user_project_id: str):
    try:
        conn = get_openstack_conn(project_id=user_project_id)
        neutron.delete_port_forwarding(conn, fip_id=data.fip_id, pf_id=data.pf_id)
        return {"message": "포트포워딩 삭제됨"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/port-forwarding/add")
def add_port_forwarding(data: PortForwardingRequest, user_project_id: str):
    conn = get_openstack_conn(project_id=user_project_id)
    existing = neutron.get_port_forwardings(conn, data.fip_id)
    if len(existing) >= 5:
        raise HTTPException(status_code=400, detail="최대 포트포워딩 수를 초과했습니다.")
    try:
        pf = neutron.create_port_forwarding(
            conn,
            fip_id=data.fip_id,
            internal_ip=data.internal_ip,
            internal_port=data.internal_port,
            external_port=data.external_port,
            protocol=data.protocol
        )
        return {"message": "포트포워딩 생성됨", "pf": pf.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트포워딩 생성 실패: {e}")