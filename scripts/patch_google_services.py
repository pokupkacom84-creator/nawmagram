#!/usr/bin/env python3
"""Клонирует записи google-services.json под пакет org.fluxgram.product (и .beta/.web варианты)."""
import json, copy, sys, os

OLD = "org.telegram.messenger"
NEW = "org.fluxgram.product"

paths = [
    "telegram/TMessagesProj/google-services.json",
    "telegram/TMessagesProj_App/google-services.json",
]
found_any = False
for gs_path in paths:
    if not os.path.exists(gs_path):
        continue
    found_any = True
    with open(gs_path) as f:
        data = json.load(f)

    def pkg_of(c):
        return c.get("client_info", {}).get("android_client_info", {}).get("package_name", "")

    existing = {pkg_of(c) for c in data.get("client", [])}
    new_clients = []
    for client in data.get("client", []):
        pkg = pkg_of(client)
        if pkg.startswith(OLD):
            new_pkg = NEW + pkg[len(OLD):]
            if new_pkg in existing:
                continue
            existing.add(new_pkg)
            clone = copy.deepcopy(client)
            clone["client_info"]["android_client_info"]["package_name"] = new_pkg
            new_clients.append(clone)

    data["client"].extend(new_clients)
    with open(gs_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"{gs_path}: added {len(new_clients)} fluxgram entries")

if not found_any:
    print("google-services.json not found, skipping")
