# -*- coding: utf-8 -*-

import json
import requests
import ovh
import os
import re
import socket

ip_regex = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
HA_SUBDOMAIN_A_TTL = 60  # seconds

etc_hosts = {}

## binding individual IPs to the domain (requests ignores the Host: header!!!) is stolen from
## https://stackoverflow.com/questions/29995133/python-requests-use-navigate-site-by-servers-ip/63185592#63185592
# decorate python built-in resolver
def custom_resolver(builtin_resolver):
    def wrapper(*args, **kwargs):
        try:
            return etc_hosts[args[:2]]
        except KeyError:
            # fall back to builtin_resolver for endpoints not in etc_hosts
            return builtin_resolver(*args, **kwargs)

    return wrapper


# monkey patching
socket.getaddrinfo = custom_resolver(socket.getaddrinfo)

def _bind_ip(domain_name, port, ip):
    '''
    resolve (domain_name,port) to a given ip
    '''
    key = (domain_name, port)
    # (family, type, proto, canonname, sockaddr)
    value = (socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM, 6, '', (ip, port))
    etc_hosts[key] = [value]

def main():
    client = ovh.Client(
        endpoint=os.environ["OVH_ENDPOINT"],
        application_key=os.environ["OVH_APP_KEY"],
        application_secret=os.environ["OVH_APP_SECRET"],
        consumer_key=os.environ["OVH_CONSUMER_KEY"],
    )
    domain = os.environ['OVH_DOMAIN']
    ha_subdomain = os.environ["OVH_HA_SUBDOMAIN"]
    node_subdomains = os.getenv("OVH_NODE_SUBDOMAINS", "").split(",")
    node_ips = os.getenv("OVH_NODE_IPS", "").split(",")

    for sd in node_subdomains:
        if not sd:
            continue
        e = client.get(f"/domain/zone/{domain}/record", fieldType="A", subDomain=sd)
        entry_id = client.get(f"/domain/zone/{domain}/record", fieldType="A", subDomain=sd)[0]
        node_ips.append(client.get(f"/domain/zone/{domain}/record/{entry_id}")["target"])

    node_ips = dict.fromkeys(set([x for x in node_ips if re.match(ip_regex, x)]), False)

    for ip in node_ips.keys():
        try:
            _bind_ip(f"{ha_subdomain}.{domain}", 443, ip)
            r = requests.get(f"https://{ha_subdomain}.{domain}/", timeout=2, verify=True)
            node_ips[ip] = (r.status_code == 200)
        except requests.exceptions.Timeout:
            node_ips[ip] = False

    print("Node ips and current availability", node_ips)

    current_ha_entry_ids = client.get(
            f"/domain/zone/{domain}/record",
            fieldType="A",
            subDomain=ha_subdomain
            )
    current_ha_entries = {}
    to_add = []
    to_remove = []

    for e in current_ha_entry_ids:
        r = client.get(f"/domain/zone/{domain}/record/{e}")
        current_ha_entries[r["target"]] = r
        if r["target"] not in node_ips or not node_ips[r["target"]]:
            to_remove.append(r)  # we no longer want it, or it is not responding

    for ip, state in node_ips.items():
        if ip not in current_ha_entries and node_ips[ip]:
            to_add.append(ip)

    print("Current entries", json.dumps(current_ha_entries, indent=4))

    print(f"{to_add=}")
    print(f"{to_remove=}")

    for ip in to_add:
        result = client.post(f"/domain/zone/{domain}/record",
            fieldType="A",
            subDomain=ha_subdomain,
            target=ip,
            ttl=HA_SUBDOMAIN_A_TTL
        )
        print("adding", json.dumps(result, indent=4))

    if len(current_ha_entries) + len(to_add) - len(to_remove) > 2:
        # if not, something is very wrong, because we need at least three nodes,
        # so don't remove everything, as we may be removing good nodes that don't respond for some reason...
        for e in to_remove:
            result = client.delete(f"/domain/zone/{domain}/record/{e['id']}")
            print("removing", json.dumps(e, indent=4))

    else:
        print("Not removing anything as that would take us below 2")

    if to_add or to_remove:
        client.post(f"/domain/zone/{domain}/refresh")

if __name__ == "__main__":
    main()
