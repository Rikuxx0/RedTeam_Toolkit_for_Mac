# 再現性の阻害要因（2026-11-10）

監査中に source、package、設定、秘密情報は変更していない。以下は **実測** と **過去記録** を分けた未解決事項である。`manifests/versions.lock` の hash はローカル実体の識別子であり、公式配布物との照合をまだ保証しない。

| 優先 | 対象 | 確認した事実 / 制約 | 次フェーズ前の処置 |
|---|---|---|---|
| 高 | Git 追跡範囲 | root の唯一のコミットは `70dfa1c`。監査開始時 README に変更があり、`.gitignore`、`c2/`、`cloud/`、`docs/`、`scripts/`、`stego-toolkit/` は未追跡。`Rubeus/`、`bloodhound-ce/`、`wordlists/`、`Web_ExploitScripts/` は ignore される。clone だけでは現環境を得られない。 | 保存すべき source、Compose、patch、文書の追跡方針を決める。秘密・大容量・生成物は除外したまま。 |
| 高 | Havoc Git / submodule | `c2/Havoc` と `client/external/{spdlog,json,toml}` に個別の `.git` metadata がない。以前の記録 `c84f775...` は候補であり現在の source revision と submodule revision は確認不能。Phase 2A で3つの submodule tree hash を保存した。 | 本体と各 submodule の固定 commit を同定し、fingerprint と照合する。既存 tree を上書きしない。 |
| 高 | Havoc CMake patch | `client/CMakeLists.txt` は C++17、`string(APPEND CMAKE_CXX_FLAGS " -fpermissive")`。候補 c84f775 の raw file との差は2行。現在のファイルはスナップショットとして保存したが、全体の基準 commit は未確定。 | 正しい基準 commit を確認後、スナップショットから patch を切り出す。`/usr/bin/x86_64-w64-mingw32-*` hardcode も別途扱う。 |
| 高 | Havoc toml11 patch | `exception.hpp` の `_GNU_SOURCE`/`strerror_r` と `serializer.hpp` の `__APPLE__` 分岐をスナップショット保存。toml11 の project version 3.7.1 は現在の submodule commit を特定しない。 | 上流 commit を同定してローカル差分だけを抽出し、patch 化する。 |
| 高 | Havoc compiler/profile | 元 profile の管理 bind は `0.0.0.0:40056`。Compiler64/86 は欠落した付属 cross compiler を参照。Homebrew x86/x64 MinGW は arm64 Mach-O として存在する。以前報告された Linux ELF compiler 実行は exit 126。 | 原 profile は保持し、localhost の私用 copy と native MinGW path の再現手順を記録する。Demon build は別の承認済み環境で検証。 |
| 解消済み（一部） | NetExec patch | uv tool は Git commit `c7dc286ba65daf10402cdc470e531b84e6d3d911`。固定上流との差は `sys.exit(1)`→`sys.exit(0)` の1行のみ。`patches/netexec/version-exit-code.patch` を保存し、隔離領域で適用結果 hash を確認した。 | クリーンな uv 再構築は未検証。取得元・依存 artifact hash を固定してから installer に組み込む。 |
| 高 | 公式配布物の来歴 | Sliver Server/Client の arm64 実体と SHA-256 は記録したが、この監査で release asset URL/署名と照合していない。以前報告の Server v1.7.9 と commit は現在の binary から再取得していない。 | 公式 release の固定 URL、署名/公開 hash、asset version を確認して lock に格上げする。鍵・server data は対象外。 |
| 高 | Docker pin | Empire Compose は `bcsecurity/empire:v7.0.2`、BloodHound CE は `latest` を含む。digest 未記録。現在 image/container/volume は 0。Compose platform 指定だけでは実 image の ARM64 対応を証明できない。 | 公式 image manifest と digest を照合し、BloodHound tag を固定。Compose の volume/port と認証設定を安全に設計。 |
| 高 | 空き容量 | 空き約 3.6 GiB、使用率 99%。`c2` だけで 441 MiB、Python root venv 約 1.1 GiB。 | 取得・build・Docker 展開の容量上限を見積もり、installer が開始前に拒否できるようにする。今回 cleanup しない。 |
| 中 | Python lock | Phase 2A で3 venv と5 uv tool の環境別版数・CLI・source 種別を保存した。全8環境が Level 2。`requirements.txt` は一部のみ、wheel hash・index・解決条件は未固定。`pyvenv.cfg` と shebang はローカル絶対パス依存。 | Python minor version、index、hash 付き Level 3/4 lock と新規環境での再構築検証を行う。共有 venv 全量を標準対象にしない。 |
| 中 | Python 同名衝突 | root `certipy` 0.2.3 は Certipy-AD と未確認。Python/Go Kerbrute、Python/Brew Nuclei、Python/Brew truffleHog、Brew/root venv sqlmap、uv/root venv bloodhound-ce が重複。 | 明示的なコマンド名・優先実体を決め、PATH 検証を導入。Certipy-AD は別ツールとして扱う。 |
| 中 | Rubeus | Windows x86 PE と SHA-256、.NET Framework v4.0 target、参照アセンブリ package は存在。source revision と build command/flags は失われた。 | 上流 commit と依存 package hash、SDK、cross build 手順を固定し、無害な PE metadata 検証だけを通常テストにする。 |
| 中 | Cloud source | GraphRunner、Graphpython、GCP-Hound、GCP Scanner の source checkout に Git metadata がない。AzureHound binary には Go pseudo-version が埋まるが取得方法は未記録。 | 上流 revision、差分、ライセンスと取得 URL を確認。source tree を破壊しない。 |
| 中 | PATH / package manager | 有効 `dotnet` 10.0.101 と Brew formula 10.0.400 が相違。`kubectl` は `/usr/local/bin` の 1.34.1 を選び、Brew 登録版 1.37.2 と異なる。Brew doctor は Azure CLI formula 消失と deprecated Qt5 等を報告。 | 有効実体と package manager record を分離して検出し、固定版の入手方法を選ぶ。 |
| 中 | GUI / ライセンス | Burp、IDA Free、Wireshark、Docker の app は確認。その他 GUI は Cask 登録のみ。edition、配布 URL、署名、利用規約、初回起動は未確認。 | 自動取得可能性と手動ライセンス工程をツール別に確定。認証自動化をしない。 |
| 低 | stego-toolkit / Web PoC | stego-toolkit は Dockerfile と多数の install script を持つが image はない。Web PoC は Node lock と大型 fixture を含む。個別 script の安全性・再配布可否は未評価。 | 直接使う component を選別し、Docker は任意起動。fixture/秘密らしいファイルを default installer に含めない。 |

## ローカル patch の管理案

NetExec は [固定 commit の `nxc/cli.py`](https://github.com/Pennyw0rth/NetExec/blob/c7dc286ba65daf10402cdc470e531b84e6d3d911/nxc/cli.py) を基準に1行の patch を保存した。Havoc は基準 commit が不明なため、安全な最小スナップショットと source fingerprint に留めた。どちらも既存インストール先には適用していない。上流更新時は hash と `git apply --check` 相当を先に確認し、衝突を自動解決しない。

## Phase 2B 時点の導入制約

インストーラーの静的検証・計画・隔離fixtureテストは実装したが、現ホストへの実導入は行っていない。Homebrew Formula 46件とGo module 10件は条件付き自動導入候補で、Brew catalogの版数一致、Go module checksum、空き容量を実行時に確認する。Homebrewの推移的依存関係まで完全固定したlockはなく、依存更新の可能性を解消する必要がある。Goもmodule本体のsumを固定した段階で、全推移的moduleとtoolchainのartifact検証は未完了。Pythonの8環境はLevel 2のまま。Sliverの公式URL、Docker digest、Havocの基準revisionが未確定のため、これらは未導入ホストで自動取得できない。

Git追跡外またはignore対象の重要ファイルが残るため、現リポジトリをそのままGitHubからcloneしても109項目を再現できない。追跡方針と配布可能な資産を確定し、クリーンなmacOS arm64環境で段階的に検証する必要がある。

## 今回収集しなかったもの

API key、password、C2 証明書/秘密鍵、クラウド資格情報、認証 cookie、シェル履歴、Havoc DB 内容、Docker volume の内容、Windows 成果物の実行結果は収集していない。Compose や profile は鍵名・公開範囲だけを評価し、秘密値を報告していない。
