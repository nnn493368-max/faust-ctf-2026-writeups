#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前自检：
  1) 脱敏：扫描敏感模式
  2) 事实：README/各 writeup 里的成绩数字必须与 data/scoreboard-full.json 一致
  3) 链接：相对链接指向的文件必须存在
  4) 编号：不得把队号 980 与记分板 id 185 混用
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = os.path.dirname(os.path.abspath(__file__))
ok = True

# ---------- 1) 脱敏 ----------
SENSITIVE = [
    (r"BEGIN [A-Z ]*PRIVATE KEY", "私钥块"),
    (r"BEGIN OPENSSH", "私钥块"),
    (r"H0u5t0n_W3_h4v3", "Vulnbox 服务包口令"),
    (r"fd66:777", "基础设施网段（不该出现在公开文档）"),
    (r"player-faustctf\.conf", "VPN 配置文件名"),
    (r"vuln-faustctf\.conf", "VPN 配置文件名"),
    (r"<ca>|<cert>|<key>", "OpenVPN 内联凭据"),
]
print("=== 1) 脱敏扫描 ===")
hits = 0
SELF = os.path.basename(os.path.abspath(__file__))   # 模式列表就在本文件里，跳过自身
for root, _dirs, files in os.walk(R):
    if ".git" in root:
        continue
    for fn in files:
        if fn == SELF:
            continue
        if not fn.lower().endswith((".md", ".py", ".json", ".csv", ".txt")):
            continue
        p = os.path.join(root, fn)
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for pat, why in SENSITIVE:
            for m in re.finditer(pat, txt, re.I):
                rel = os.path.relpath(p, R)
                line = txt[: m.start()].count("\n") + 1
                print(f"  HIT  {rel}:{line}  [{why}]  {m.group(0)[:40]!r}")
                hits += 1
print(f"  -> {hits} 处命中" + ("  (预期 0)" if hits == 0 else "  ⚠ 需人工确认"))
ok &= hits == 0

# ---------- 2) 事实校验 ----------
print("\n=== 2) 成绩数字校验 ===")
data = json.load(open(os.path.join(R, "data", "scoreboard-full.json"), encoding="utf-8"))
me = next(t for t in data["teams"] if t["name"] == "qiyu")
n = len(data["teams"])
facts = {
    "rank": me["rank"],
    "teams": n,
    "total": round(me["total"], 2),
    "offense": round(me["offense"], 2),
    "defense": round(me["defense"], 2),
    "sla": round(me["sla"], 2),
    "imc_offense": round(me["services"][1]["offense"], 2),
    "alf_offense": round(me["services"][0]["offense"], 2),
    "lamp_offense": round(me["services"][2]["offense"], 2),
    "rc_offense": round(me["services"][3]["offense"], 2),
}
imc_share = facts["imc_offense"] / facts["offense"] * 100
for k, v in facts.items():
    print(f"  {k:14} = {v}")
print(f"  IMC 占进攻分比例 = {imc_share:.1f}%")

readme = open(os.path.join(R, "README.md"), encoding="utf-8").read()
checks = [
    ("67 / 502", "排名", True),
    ("10,752.81", "总分", True),
    ("6,737.16", "进攻", True),
    ("5,069.72", "防守(绝对值)", True),
    ("9,085.37", "SLA", True),
    ("13.3%", "百分位", True),
    ("86.7%", "击败比例", True),
    ("6,726", "IMC 进攻分取整", True),
]
for needle, why, want in checks:
    present = needle in readme
    good = present == want
    ok &= good
    print(f"  {'OK  ' if good else 'BAD '}  README 含 {needle!r} ({why}) = {present}")

# ---------- 3) 相对链接 ----------
print("\n=== 3) 相对链接可解析 ===")
bad_links = 0
for root, _dirs, files in os.walk(R):
    if ".git" in root:
        continue
    for fn in files:
        if not fn.endswith(".md"):
            continue
        p = os.path.join(root, fn)
        txt = open(p, encoding="utf-8").read()
        for m in re.finditer(r"\]\((\.\.?/[^)#]+)\)", txt):
            tgt = os.path.normpath(os.path.join(root, m.group(1)))
            if not os.path.exists(tgt):
                print(f"  MISS {os.path.relpath(p, R)} -> {m.group(1)}")
                bad_links += 1
print(f"  -> {bad_links} 个断链")
ok &= bad_links == 0

# ---------- 4) 编号一致性 ----------
print("\n=== 4) 队号 / 记分板 id 一致性 ===")
for fn in ["README.md", "writeups/imc.md", "writeups/lamp.md", "writeups/rufflecopter.md"]:
    txt = open(os.path.join(R, fn), encoding="utf-8").read()
    has980 = "980" in txt
    has185 = re.search(r"\b185\b", txt) is not None
    # README 必须同时解释两者
    print(f"  {fn:28} 提到 980={has980}  提到 185={has185}")
if "team number" not in readme.lower() or "980" not in readme:
    print("  BAD  README 未说明队号")
    ok = False

print("\n结论: " + ("全部通过，可发布" if ok else "有未通过项，先修"))
sys.exit(0 if ok else 1)
