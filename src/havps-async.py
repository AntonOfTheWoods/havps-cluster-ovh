# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import json
import os
import ovh
import re

IP_REGEX = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'

async def get_status(ip, session, timeout):
    async with session.get(f"http://{ip}", headers={"Host": "am.transcrob.es"}, timeout=timeout) as response:
        return ip, response.status == 200

async def main():

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
    timeout = int(os.getenv("OVH_HA_SUBDOMAIN_TIMEOUT_SECS", "5"))

    for sd in node_subdomains:
        if not sd:
            continue
        e = client.get(f"/domain/zone/{domain}/record", fieldType="A", subDomain=sd)
        entry_id = client.get(f"/domain/zone/{domain}/record", fieldType="A", subDomain=sd)[0]
        node_ips.append(client.get(f"/domain/zone/{domain}/record/{entry_id}")["target"])

    node_ips = dict.fromkeys(set([x for x in node_ips if re.match(IP_REGEX, x)]), False)

    async with aiohttp.ClientSession() as session:
        node_ips = dict(await asyncio.gather(*[get_status(ip, session, timeout) for ip in node_ips]))

    print(node_ips)

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

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
