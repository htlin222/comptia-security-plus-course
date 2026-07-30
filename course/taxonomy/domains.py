"""主題領域分面：從單元名稱與影片標題認出這一格屬於哪幾個資安領域。

框架本身不認識任何主題，分面篩選要能用就得有一份詞彙表。這裡刻意中英關鍵字都收——
單元名稱是繁中，影片標題幾乎全是英文，只認一種語言的話分面會缺一半。
"""

from __future__ import annotations

import re

GROUPS = [
    "身分與存取",
    "密碼學",
    "網路防禦",
    "端點與系統",
    "雲端與虛擬化",
    "偵測與應變",
    "資料保護",
    "威脅與攻擊",
    "治理與風險",
    "實體與環境",
]

# 分面名 -> (所屬群組, 中英關鍵字)
FACETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "身分認證": ("身分與存取", ("認證", "authentication", "authenticat", "login", "credential", "passwordless")),
    "多因子": ("身分與存取", ("多因子", "mfa", "2fa", "two.factor", "multifactor", "otp", "totp")),
    "授權與權限": ("身分與存取", ("授權", "權限", "authorization", "rbac", "abac", "dac", "mac", "least privilege", "permission")),
    "單一登入與聯邦": ("身分與存取", ("單一登入", "聯邦", "sso", "single sign", "federation", "saml", "oauth", "oidc", "kerberos")),
    "特權存取": ("身分與存取", ("特權", "privileged", "pam", "admin account", "sudo")),
    "零信任": ("身分與存取", ("零信任", "zero.trust", "ztna", "sdp")),

    "加解密": ("密碼學", ("加密", "解密", "encrypt", "decrypt", "cipher", "aes", "rsa", "symmetric", "asymmetric")),
    "雜湊與簽章": ("密碼學", ("雜湊", "簽章", "hash", "hashing", "signature", "sha", "md5", "hmac", "salt")),
    "PKI 與憑證": ("密碼學", ("憑證", "pki", "certificate", "ca ", "x.509", "csr", "ocsp", "crl", "tls", "ssl")),
    "金鑰管理": ("密碼學", ("金鑰", "key management", "key exchange", "hsm", "escrow", "diffie")),

    "防火牆": ("網路防禦", ("防火牆", "firewall", "waf", "ngfw", "utm", "acl")),
    "網路分段": ("網路防禦", ("分段", "分區", "segmentation", "vlan", "dmz", "microsegment", "subnet")),
    "VPN 與通道": ("網路防禦", ("vpn", "ipsec", "通道", "tunnel", "wireguard")),
    "代理與負載平衡": ("網路防禦", ("代理", "負載平衡", "proxy", "load balanc", "reverse proxy", "cdn")),
    "無線安全": ("網路防禦", ("無線", "wireless", "wifi", "wi-fi", "wpa", "802.11", "bluetooth")),
    "網路存取控制": ("網路防禦", ("nac", "802.1x", "port security", "network access control")),

    "系統強化": ("端點與系統", ("強化", "harden", "baseline", "patch", "配置管理", "configuration management", "group policy")),
    "端點防護": ("端點與系統", ("端點", "endpoint", "edr", "xdr", "antivirus", "防毒", "host.based", "hids", "hips")),
    "嵌入式與工控": ("端點與系統", ("嵌入式", "工控", "embedded", "scada", "ics", "iot", "rtos", "plc")),
    "行動裝置": ("端點與系統", ("行動裝置", "mobile", "byod", "mdm", "android", "ios ")),

    "雲端安全": ("雲端與虛擬化", ("雲端", "cloud", "aws", "azure", "gcp", "saas", "iaas", "paas", "責任共擔", "shared responsibility")),
    "容器與無伺服器": ("雲端與虛擬化", ("容器", "container", "docker", "kubernetes", "k8s", "serverless", "lambda")),
    "虛擬化": ("雲端與虛擬化", ("虛擬", "virtual machine", "hypervisor", "vm ", "virtualiz")),
    "基礎設施即程式碼": ("雲端與虛擬化", ("基礎設施即程式碼", "infrastructure as code", "terraform", "ansible", "iac")),

    "日誌與監控": ("偵測與應變", ("日誌", "監控", "log", "logging", "monitor", "netflow", "snmp", "syslog")),
    "SIEM 與 SOAR": ("偵測與應變", ("siem", "soar", "security operations center", "soc ", "correlation")),
    "入侵偵測": ("偵測與應變", ("入侵偵測", "入侵防禦", "ids", "ips", "intrusion", "nids")),
    "事件應變": ("偵測與應變", ("事件應變", "incident response", "incident", "containment", "playbook", "tabletop")),
    "數位鑑識": ("偵測與應變", ("鑑識", "forensic", "chain of custody", "e-discovery", "memory dump", "autopsy")),
    "威脅情報與獵捕": ("偵測與應變", ("威脅情報", "獵捕", "threat intel", "threat hunt", "ioc", "ttp", "att&ck", "osint")),
    "弱點管理": ("偵測與應變", ("弱點管理", "vulnerability scan", "vulnerability management", "cvss", "nessus", "patch management")),

    "資料分級": ("資料保護", ("分級", "classification", "data owner", "data steward", "labeling")),
    "資料外洩防護": ("資料保護", ("外洩防護", "dlp", "data loss prevention", "exfiltration")),
    "備份與復原": ("資料保護", ("備份", "復原", "backup", "restore", "rto", "rpo", "disaster recovery", "raid")),
    "隱私": ("資料保護", ("隱私", "privacy", "gdpr", "pii", "phi", "匿名", "anonym", "pseudonym", "tokeniz")),

    "社交工程": ("威脅與攻擊", ("社交工程", "social engineering", "phishing", "釣魚", "pretext", "vishing", "smishing", "impersonat")),
    "惡意程式": ("威脅與攻擊", ("惡意程式", "malware", "virus", "worm", "trojan", "rootkit", "spyware", "ransomware", "勒索")),
    "注入與應用攻擊": ("威脅與攻擊", ("注入", "injection", "sql", "xss", "csrf", "buffer overflow", "race condition", "deserializ")),
    "網路攻擊": ("威脅與攻擊", ("ddos", "dos ", "on.path", "man.in.the.middle", "arp", "spoof", "replay", "dns attack", "poison")),
    "密碼攻擊": ("威脅與攻擊", ("密碼攻擊", "password attack", "brute force", "credential stuffing", "spraying", "rainbow table")),
    "供應鏈": ("威脅與攻擊", ("供應鏈", "supply chain", "third.party", "第三方", "vendor")),

    "治理": ("治理與風險", ("治理", "governance", "policy", "政策", "標準", "standard", "procedure", "grc")),
    "風險管理": ("治理與風險", ("風險", "risk", "ale", "sle", "aro", "risk register", "bia", "衝擊分析")),
    "法遵": ("治理與風險", ("法遵", "合規", "compliance", "hipaa", "pci", "sox", "iso 27001", "nist csf", "法規")),
    "稽核": ("治理與風險", ("稽核", "audit", "assessment", "attestation", "penetration test", "滲透測試", "pentest")),
    "營運持續": ("治理與風險", ("營運持續", "business continuity", "bcp", "resilien", "韌性", "備援", "redundan", "failover")),
    "人員與教育": ("治理與風險", ("意識訓練", "awareness", "training", "教育", "onboarding", "offboarding")),

    "實體安全": ("實體與環境", ("實體", "physical security", "badge", "mantrap", "vestibule", "bollard", "fence", "cctv", "guard", "lock")),
    "誘捕技術": ("實體與環境", ("誘捕", "欺敵", "honeypot", "honeynet", "honeyfile", "honeytoken", "deception")),
}

GROUP_OF = {name: group for name, (group, _) in FACETS.items()}

_PATTERNS = {
    name: re.compile("|".join(re.escape(k) if not any(c in k for c in ".[]") else k for k in kws), re.I)
    for name, (_, kws) in FACETS.items()
}


def extract(*texts: str | None) -> list[str]:
    """回傳這段文字命中的分面，順序固定（依 FACETS 宣告順序），方便 diff。"""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return []
    return [name for name, pat in _PATTERNS.items() if pat.search(blob)]
