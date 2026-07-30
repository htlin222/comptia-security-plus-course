"""影片類別：把每支延伸影片歸到一個主題家族，好在類別層級掛標準依據。

單元層級的實證只講「這個主題的標準怎麼寫」，類別層級講的是「這一整類做法的依據」，
兩層都有才不會出現「單元說得頭頭是道、底下影片教的做法卻沒人背書」。
"""

from __future__ import annotations

import re

NAMES = {
    "crypto": "密碼學與金鑰",
    "identity": "身分與存取管理",
    "netdef": "網路邊界防禦",
    "detect": "偵測、監控與日誌",
    "respond": "事件應變與數位鑑識",
    "vuln": "弱點與修補管理",
    "cloud": "雲端、容器與虛擬化",
    "data": "資料保護與隱私",
    "govern": "治理、風險與法遵",
    "threat": "威脅手法與社交工程",
}

# 由上而下比對，先命中的贏。順序是刻意的：專有名詞排前面，通稱排後面，
# 否則 "security policy" 這種字會把所有東西都吸進 govern。
RULES: list[tuple[str, str]] = [
    ("crypto", r"encrypt|decrypt|cipher|aes|rsa|hash|sha-?\d|signature|pki|certificat|tls|ssl|key exchange|hsm|diffie|cryptograph|obfuscat"),
    ("identity", r"authenticat|authoriz|mfa|2fa|multifactor|sso|single sign|saml|oauth|oidc|kerberos|rbac|abac|iam\b|identity|privileged|pam\b|password polic|least privilege|access control"),
    ("netdef", r"firewall|vpn|ipsec|vlan|segment|dmz|proxy|load balanc|802\.1x|nac\b|wireless|wifi|wi-fi|wpa|port security|network appliance|ids\b|ips\b|intrusion|embedded|scada|\bics\b|\biot\b|rtos|\bplc\b|operational technology|\bot\b security"),
    ("detect", r"siem|soar|\bsoc\b|log|logging|monitor|netflow|syslog|snmp|threat hunt|threat intel|detection|edr|xdr|telemetry|correlat"),
    ("respond", r"incident|forensic|chain of custody|containment|playbook|tabletop|breach response|disaster recovery|backup|restore|\brto\b|\brpo\b|continuity|resilien|redundan|failover|high availability|\braid\b|韌性|備援"),
    ("vuln", r"vulnerab|patch|cvss|cve\b|scan|nessus|pentest|penetration test|bug bounty|hardening|harden|baseline"),
    ("cloud", r"cloud|aws|azure|gcp|saas|iaas|paas|container|docker|kubernetes|k8s|serverless|lambda|hypervisor|virtual machine|virtualiz|terraform|infrastructure as code"),
    ("data", r"\bdlp\b|data loss|classification|privacy|gdpr|\bpii\b|\bphi\b|anonym|pseudonym|token(iz|is)|masking|data at rest|data in transit|retention|cia triad|confidentiality|integrity"),
    ("threat", r"phishing|social engineering|malware|virus|worm|trojan|rootkit|ransomware|ddos|\bdos\b|spoof|injection|\bxss\b|\bcsrf\b|buffer overflow|brute force|credential stuffing|attack|exploit|threat actor"),
    ("govern", r"change management|變更管理|configuration management|governance|polic|standard|procedure|compliance|audit|risk|\bgrc\b|hipaa|\bpci\b|\bsox\b|iso ?27001|nist|framework|awareness|training|third.party|vendor|agreement|\bsla\b"),
]

_COMPILED = [(cid, re.compile(pat, re.I)) for cid, pat in RULES]


def classify(drill: dict) -> str | None:
    blob = " ".join(str(drill.get(k) or "") for k in ("name", "title", "why", "channel"))
    for cid, pat in _COMPILED:
        if pat.search(blob):
            return cid
    return None
