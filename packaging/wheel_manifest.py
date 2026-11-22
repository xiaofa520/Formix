"""Write the hash-checked offline install input from the resolved lock."""
import re

def write_offline_requirements(packages, folder):
    lines = []
    for package in packages:
        spec = package.get("archive") or package["wheels"][0]
        digest = spec.get("hashes", {}).get("sha256", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"Missing SHA-256 for {package['name']}")
        lines.append(f"{package['name']}=={package['version']} --hash=sha256:{digest}")
    path = folder / "offline.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
