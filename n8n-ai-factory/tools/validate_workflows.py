#!/usr/bin/env python3
"""Structural validation of the generated n8n workflows:
- JSON parses, node names unique
- every connection source/target references an existing node
- every Code node's JavaScript parses (wrapped in an async function,
  mirroring how n8n executes it)
"""
import json
import os
import subprocess
import sys
import tempfile

WF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflows")
ALLOWED_TYPES = {
    "n8n-nodes-base.webhook", "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.code", "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.postgres", "n8n-nodes-base.if",
    "n8n-nodes-base.stickyNote", "n8n-nodes-base.splitInBatches",
}

failures = []

for filename in sorted(os.listdir(WF_DIR)):
    if not filename.endswith(".json"):
        continue
    path = os.path.join(WF_DIR, filename)
    with open(path, encoding="utf-8") as fh:
        wf = json.load(fh)
    names = [n["name"] for n in wf["nodes"]]
    if len(names) != len(set(names)):
        failures.append(f"{filename}: duplicate node names")
    name_set = set(names)
    for n in wf["nodes"]:
        if n["type"] not in ALLOWED_TYPES:
            failures.append(f"{filename}: unexpected node type {n['type']}")
    for src, outs in wf["connections"].items():
        if src not in name_set:
            failures.append(f"{filename}: connection source '{src}' not a node")
        for branch in outs.get("main", []):
            for edge in branch:
                if edge["node"] not in name_set:
                    failures.append(f"{filename}: connection target '{edge['node']}' not a node")
    # JS syntax check for Code nodes
    for n in wf["nodes"]:
        if n["type"] != "n8n-nodes-base.code":
            continue
        js = n["parameters"]["jsCode"]
        wrapped = "async function __n8n_code($input, $env, $, $json) {\n" + js + "\n}\n"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(wrapped)
            tmp = tf.name
        proc = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        if proc.returncode != 0:
            failures.append(f"{filename}: JS syntax error in '{n['name']}':\n{proc.stderr[:600]}")
    connected = set(wf["connections"].keys())
    targets = {e["node"] for outs in wf["connections"].values()
               for branch in outs.get("main", []) for e in branch}
    orphans = [nm for nm in names
               if nm not in connected and nm not in targets and nm != "Sticky Note"]
    if orphans:
        failures.append(f"{filename}: unconnected nodes: {orphans}")
    print(f"{filename}: {len(names)} nodes, {sum(len(b) for o in wf['connections'].values() for b in o.get('main', []))} edges — checked")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nAll workflows structurally valid, all Code-node JavaScript parses.")
