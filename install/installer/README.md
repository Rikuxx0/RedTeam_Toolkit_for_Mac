# インストーラー実装

`install.sh` はmacOS arm64とPython 3.10以上を確認して `installer.main` を起動する。`manifest.py` は現在のManifestで使うYAMLの限定構文だけを標準ライブラリで解析し、未知の構文を拒否する。`core.py` は依存解決、読み取り専用検出、導入計画、`backends.py` は承認後の個別導入を担当する。C2の起動・停止や公式CLIの代替は行わない。

現在のManifestで自動導入の候補になるのはHomebrew Formula 46件と、Go checksumを固定したmodule 10件。Homebrewは実際のcatalog version一致を実行直前に確認する。Goはmodule sumを照合し、一時領域でarm64バイナリを作って、既存ファイルを置換せず配置する。公式バイナリ、Docker digest、固定Gitソース用Backendもあるが、現Manifestで必要なURL・digest・リビジョンが未確定の対象は保留する。Pythonの8環境はLevel 2のため、既存環境の照合だけを行い、自動再構築しない。Havocのスナップショットは自動適用しない。NetExecのパッチは既存uv環境の状態判定に使い、自動再適用しない。

Homebrewの実導入前には既存の依存Formulaに更新が必要かも読み取り専用で確認し、判定不能または更新が必要なら停止する。依存Formulaを含む完全なartifact lockは未完成であり、候補数は再現成功を保証しない。

BackendはManifestの `verification.command` を実行しない。あの値は監査資料であり、任意のManifest文字列をシェルに渡さない。外部コマンドは固定された引数配列で実行し、`eval` と `shell=True` を使わない。Brew/Go/Binary/Docker/Gitの各操作は、計画表示と明示的確認の後に限る。`--list`、`--audit`、`--dry-run`、`--verify` はログも作らない。

戻り値は `0` が完了または読み取り専用成功、`1` がBackend実行失敗、`2` が保留・競合などの未完了、`3` がManifest/環境/確認の不備。実インストール時の結果だけをユーザーの `Library/Logs/RedTeam_Toolkit_for_Mac/installer.jsonl` に記録し、Git管理外に置く。

テストは `python3 -m unittest discover -s tests/installer -v`。実際のHomebrew、Go、Docker、ネットワーク操作はモック化している。CIはLinux上で静的検証と読み取り専用計画を実行するため、macOS上の実導入成功を証明しない。
