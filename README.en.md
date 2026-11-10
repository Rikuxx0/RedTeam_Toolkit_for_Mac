# RedTeam_Toolkit_for_Mac

[Japanese](README.md) / [English](README.en.md)

This is a toolkit designed for red team exercises and penetration testing on macOS systems equipped with Apple Silicon. It is intended for use on bare-metal systems; if you typically use macOS and find it difficult to set up a virtual environment such as Kali Linux, running this installer allows you to set up a minimal environment for manual penetration testing and red team exercises. Additionally, you can use your own penetration testing tools, OSINT tools, and red team tools in conjunction with this toolkit as needed.

Translated with DeepL.com (free version)

## Use cases

- Boot2Root CTF labs on platforms such as TryHackMe and Hack The Box. The author uses this toolkit regularly for those labs.
- Red team exercises and manual penetration tests performed from macOS.
- Combining the native macOS environment with other security tools.
- Quickly performing manual checks during TLPT-style exercises or hybrid workflows that include AI-assisted testing.

## Requirements

| Type | Requirement |
|---|---|
| Required | macOS running natively on Apple Silicon (ARM64), Bash, and Python 3.10 or newer. Git is needed to clone the repository. |
| Installing tools | Depending on the selection: Homebrew, Go, Git, and network access. The wordlists included in standard installation require at least 16 GiB of free disk space before download. |
| Docker-based tools | Install and start Docker Desktop, including Docker Engine and Compose, beforehand. |

The public installer and manifest are in `install/`. Tools retain their official CLIs and GUIs. Installation does not automatically start C2 services or Docker containers, and the installer itself needs no extra Python packages. Docker is not required for `--help`, `--list`, or `--dry-run`.

### Installation

```sh
git clone https://github.com/Rikuxx0/RedTeam_Toolkit_for_Mac.git
cd RedTeam_Toolkit_for_Mac/install
./install.sh --help
./install.sh --list
./install.sh --dry-run
./install.sh                 # Show the plan and install only after explicit confirmation
```

## Penetration testing and red team tools

| Area | Count | Tools |
|---|---:|---|
| C2 | 4 | Sliver Server, Sliver Client, Havoc Teamserver / GUI, Empire / Starkiller |
| Active Directory | 9 | NetExec, Certipy-AD, BloodHound CE, bloodhound-ce-python, Kerbrute, Impacket, dploot, pypykatz, Responder |
| Windows only | 2 | Rubeus, Mimikatz |
| Cloud and Kubernetes | 17 | AWS CLI, Azure CLI, Google Cloud CLI, AzureHound, Graphpython, GraphRunner, ROADtx, ROADrecon, Principal Mapper, GCP-Hound, GCP Scanner, kubectl, KubeHound, kind, IAMhounddog, aws-enumerator, GoAWSConsoleSpray |
| Network | 14 | Nmap, Masscan, Aircrack-ng, Bettercap, RustScan, Hydra, tcpdump, dnsmap, sslscan, testssl, mitmproxy, Scapy, ProxyChains-NG, socat |
| Web | 20 | Nuclei, ffuf, feroxbuster, Gobuster, sqlmap, WPScan, Amass, Subfinder, dirsearch, git-dumper, hakrawler, gauplus, waybackurls, subzy, github-subdomains, Web Exploit Scripts, wafw00f, DNSRecon, dnstwist, gf |
| Forensics and analysis | 12 | stego-toolkit, Binwalk, ExifTool, Foremost, Volatility 3, angr, YARA, radare2, JADX, osquery, oletools, Frida tools |
| GUI | 7 | Wireshark, Burp Suite, IDA Free, Binary Ninja Free, Cutter, Maltego, ZAP |
| Credential auditing | 4 | Hashcat, John the Ripper Jumbo, Medusa, Crunch |
| DevSecOps | 3 | Grype, Semgrep, TruffleHog |
| OSINT | 3 | Recon-ng, Sherlock, theHarvester |
| Framework | 1 | Metasploit |
| Wordlists | 1 | Wordlist Collection |
| Runtimes and build dependencies | 13 | Docker Desktop / Compose, Python, Go, AppleClang, Node.js, Ruby, CMake, Qt 5, MinGW-w64, .NET SDK, PowerShell, uv, pipx |

Check the current installation state with `./install.sh --list` or `--audit`. See the [usage guide](install/docs/installer-usage.md) (Japanese) for details.

Wordlists are included in all three profiles: `minimal`, `standard`, and `full`. From `install/`, review `./install.sh --dry-run` first. The installer fetches ten Git repositories at pinned commits and never updates or overwrites an existing `wordlists/` checkout. The actual download size is unverified, so at least 16 GiB of free disk space is required before starting.

**Note:** Mimikatz is not downloaded automatically or bundled with this repository because security products may detect or quarantine it, interrupting installation. If needed, obtain it manually from the [official releases](https://github.com/gentilkiwi/mimikatz/releases).
