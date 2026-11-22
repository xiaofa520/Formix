"""Read CPU and display adapter names locally, independently of encoder support."""
import ctypes
import json
import platform
import re
import subprocess
from pathlib import Path


def _output(*args):
    try:
        return subprocess.check_output(args, timeout=8, stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                       ).decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows():
    import winreg
    cpu = ""
    adapters = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\VIDEO") as devices:
            for i in range(winreg.QueryInfoKey(devices)[1]):
                name, path, _ = winreg.EnumValue(devices, i)
                if not re.fullmatch(r"\\Device\\Video\d+", name, re.I):
                    continue
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path.split("\\", 3)[3]) as key:
                        device_id = winreg.QueryValueEx(key, "MatchingDeviceId")[0]
                        if device_id.lower().startswith(("pci\\", "acpi\\", "usb\\")):
                            adapters.append(winreg.QueryValueEx(key, "DriverDesc")[0])
                except (OSError, IndexError):
                    continue
    except OSError:
        pass
    if not adapters:
        adapters = _output("powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                           "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                           "(Get-CimInstance Win32_VideoController | Where-Object "
                           "{$_.PNPDeviceID -match '^(PCI|ACPI|USB)\\\\'}).Name").splitlines()
    return cpu, adapters


def hardware_names():
    system = platform.system()
    if system == "Windows":
        cpu, adapters = _windows()
    elif system == "Darwin":
        cpu = _output("sysctl", "-n", "machdep.cpu.brand_string")
        try:
            records = json.loads(_output("system_profiler", "SPDisplaysDataType", "-json"))
            adapters = [card.get("sppci_model") or card.get("_name") for card in records.get("SPDisplaysDataType", [])]
        except ValueError:
            adapters = []
    else:
        cpu = ""
        try:
            info = Path("/proc/cpuinfo").read_text(errors="replace")
            match = re.search(r"^(?:model name|Hardware)\s*:\s*(.+)", info, re.M)
            if match:
                cpu = match.group(1).strip()
        except OSError:
            pass
        adapters = re.findall(r"(?:VGA compatible controller|3D controller|Display controller): (.+)",
                              _output("lspci"))
    cpu = re.sub(r"\((?:R|TM)\)|[®™]", "", cpu or platform.processor(), flags=re.I)
    cpu = re.sub(r"^\d+(?:st|nd|rd|th) Gen\s+", "", cpu, flags=re.I)
    cpu = re.sub(r"\bIntel Core (i[3579]-)", r"Intel \1", cpu, flags=re.I)
    cpu = re.sub(r"\s+(?:CPU\s+)?@\s*[\d.]+\s*GHz.*$|\s+\d+-Core Processor$|\s+with Radeon .*Graphics$", "", cpu, flags=re.I)
    models = []
    for name in adapters:
        if not name or re.search(r"virtual|orayidd|indirect display|remote display|basic (?:display|render)|vmware|virtio|qxl|parallels|hyper-v|microsoft hyper", name, re.I):
            continue
        name = re.sub(r"\bGeForce\s+(?=(?:RTX|GTX|GT)\b)|\s+Laptop GPU\b|\s+\(rev [0-9a-f]+\)$", "", name, flags=re.I)
        name = name.replace("NVIDIA Corporation ", "NVIDIA ").strip()
        if name and name not in models:
            models.append(name)
    return " ".join(cpu.split()), models


def cuda_driver_version():
    """Return the CUDA driver API version when a CUDA device is usable."""
    system = platform.system()
    try:
        if system == "Windows":
            driver = ctypes.WinDLL("nvcuda.dll", winmode=0x800)
        elif system == "Linux":
            driver = ctypes.CDLL("libcuda.so.1")
        else:
            return None
        devices = ctypes.c_int()
        version = ctypes.c_int()
        if (driver.cuInit(0) or driver.cuDeviceGetCount(ctypes.byref(devices))
                or devices.value < 1 or driver.cuDriverGetVersion(ctypes.byref(version))):
            return None
        return f"{version.value // 1000}.{version.value % 1000 // 10}"
    except (OSError, AttributeError):
        return None
