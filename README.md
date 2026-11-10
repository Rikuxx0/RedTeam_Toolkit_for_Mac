# Red Team Toolkit for MacOS

[日本語](README.md) / [English](README.en.md)

Appleシリコン搭載のMacOSを対象とした、レッドチーム演習およびペネトレーションテスト用のツールキットです。ベアメタルでの利用を前提としており、普段使いがMacOSであり、Kali Linuxなどの仮想環境の立ち上げが困難である場合、本インストーラーを実行することで手動ぺネトレーションテスト・レッドチーム演習環境を最低限で構築することが可能です。また、必要に応じて独自のペネトレーションテストツールやOSINTツール、レッドチームツールを併用することが可能です。

## ユースケース

- TryHackMeやHackTheBox等におけるBoot2Root CTFにおいて、最低限のツールながら、ラボ攻略することが可能です。(現に筆者が常用で攻略中)
- レッドチーム演習・手動ペネトレーションテストの実施の際に、MacOSで検証することが可能です。
- ベアメタルであるため、他のセキュリティツールと組み合わせることが可能です。
- TLPT相当のレッドチーム演習・手動ペネトレーションテスト実施やAIレッドチーム演習・ペネトレーションテストによる半自動化侵入テストにおいて、手動検証を素早く実施可能であるため、ハイブリッド検証にも有効です。

## 必要要件

| 区分 | 要件 |
|---|---|
| 必須 | Apple Silicon（ARM64）でネイティブ実行するmacOS、Bash、Python 3.10以上。クローンにはGitが必要です。 |
| ツール導入時 | 対象に応じてHomebrew、Go、Git、ネットワーク接続が必要です。標準導入に含むワードリストの取得前には16 GiB以上の空き容量が必要です。 |
| Docker対象を利用する場合 | Docker Desktop（Docker Engine・Composeを含む）を事前に導入・起動してください。 |

公開用インストーラーとManifestは `install/` にあります。既存ツールの公式CLI・GUIを利用し、C2サービスやDockerコンテナはインストール時に自動起動せず、インストーラー本体に追加のPythonパッケージは不要です。また、`--help`、`--list`、`--dry-run` にDockerは不要で、インストーラーがDockerコンテナを自動起動することもありません。

### インストール手順

以下のようにインストールを行なってください。

```sh
git clone https://github.com/Rikuxx0/RedTeam_Toolkit_for_Mac.git
cd RedTeam_Toolkit_for_Mac/install
./install.sh --help
./install.sh --list
./install.sh --dry-run
./install.sh                 # 計画表示と明示的な確認後に導入
```

## ペネトレーションテスト・レッドチームツール一覧

| 分野 | 件数 | ツール |
|---|---:|---|
| C2 | 4 | Sliver Server、Sliver Client、Havoc Teamserver / GUI、Empire / Starkiller |
| Active Directory | 9 | NetExec、Certipy-AD、BloodHound CE、bloodhound-ce-python、Kerbrute、Impacket、dploot、pypykatz、Responder |
| Windows専用 | 2 | Rubeus、Mimikatz |
| クラウド・Kubernetes | 17 | AWS CLI、Azure CLI、Google Cloud CLI、AzureHound、Graphpython、GraphRunner、ROADtx、ROADrecon、Principal Mapper、GCP-Hound、GCP Scanner、kubectl、KubeHound、kind、IAMhounddog、aws-enumerator、GoAWSConsoleSpray |
| ネットワーク | 14 | Nmap、Masscan、Aircrack-ng、Bettercap、RustScan、Hydra、tcpdump、dnsmap、sslscan、testssl、mitmproxy、Scapy、ProxyChains-NG、socat |
| Web | 20 | Nuclei、ffuf、feroxbuster、Gobuster、sqlmap、WPScan、Amass、Subfinder、dirsearch、git-dumper、hakrawler、gauplus、waybackurls、subzy、github-subdomains、Web Exploit Scripts、wafw00f、DNSRecon、dnstwist、gf |
| フォレンジック・解析 | 12 | stego-toolkit、Binwalk、ExifTool、Foremost、Volatility 3、angr、YARA、radare2、JADX、osquery、oletools、Frida tools |
| GUI | 7 | Wireshark、Burp Suite、IDA Free、Binary Ninja Free、Cutter、Maltego、ZAP |
| 認証監査 | 4 | Hashcat、John the Ripper Jumbo、Medusa、Crunch |
| DevSecOps | 3 | Grype、Semgrep、TruffleHog |
| OSINT | 3 | Recon-ng、Sherlock、theHarvester |
| フレームワーク | 1 | Metasploit |
| ワードリスト | 1 | Wordlist Collection |
| 実行基盤・開発依存 | 13 | Docker Desktop / Compose、Python、Go、AppleClang、Node.js、Ruby、CMake、Qt 5、MinGW-w64、.NET SDK、PowerShell、uv、pipx |

また、導入状態は `./install.sh --list` または `--audit` で確認できます。詳細は[使用方法](install/docs/installer-usage.md)を参照してください。

ワードリストは `minimal`・`standard`・`full` のすべてに含まれます。`./install.sh --dry-run`で予定を確認してください。10個のGitリポジトリを固定コミットで取得し、既存の`wordlists/`は更新・上書きしません。実際の取得量は未検証のため、開始前に16 GiB以上の空き容量を要求します。

**注意**

Mimikatzについて、Windows Defenderや他社のウイルス検知システムにより、本インストーラーの障害を防ぐために、インストーラーによる自動ダウンロードやリポジトリへの同梱は行っていません。

必要な場合、公式Releasesから入手してください。

[公式Releases](https://github.com/gentilkiwi/mimikatz/releases)
