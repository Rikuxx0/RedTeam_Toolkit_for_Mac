# インストーラー使用方法

対応環境はmacOS arm64ネイティブ、Python 3.10以上。`install.sh` はツール導入と検証のみを担当し、C2 Server・Dockerコンテナを自動起動しない。初回は必ず計画を確認する。

```sh
./install.sh --help
./install.sh --list
./install.sh --audit
./install.sh --dry-run
./install.sh --verify
./install.sh --profile minimal --dry-run
./install.sh --profile standard --dry-run
./install.sh --profile full --dry-run
./install.sh --category ad --dry-run
./install.sh --category cloud --dry-run
./install.sh --category c2 --dry-run
./install.sh --category web --dry-run
./install.sh --tool netexec --dry-run
./install.sh --tool sliver --dry-run
```

フィルターなしの通常実行は `standard`。`--tool sliver` はManifestの別名でServerとClientの2項目を選ぶ。`--category` と `--tool` は同時に使えない。依存ツールはカテゴリー外でも追加される。`--list` は109項目の現在状態を表示し、`--audit` は読み取り専用の実体検出、`--verify` はパッケージ登録・Go build metadata・Python package一覧・ローカルSHA-256などを確認する。外部対象へのスキャンやC2接続はしない。`--json` は読み取り専用モードで使える。

現Manifestの選択数は `minimal` 6件、`standard` 31件、`full` 109件（依存を含む）。導入方式上の条件付き自動化候補はHomebrew Formula 46件とGo module 10件で、残る53件は手動工程または固定情報不足で保留する。これらは新規Macでの導入成功数を意味しない。

実導入では、対象と状態、予定操作、既知の必要容量、容量不明の操作数を先に表示する。対話端末では `INSTALL` の入力が必要。容量不明の取得・ビルドは追加で `UNKNOWN` の入力が必要。非対話環境で明示する場合は `--yes --accept-unknown-size` を指定する。これらのフラグはManifestの未確定情報や不一致によるブロックを解除しない。現在のMacでの通常確認には `--dry-run` を使う。

状態の意味は `verified` がローカルの版数・hash等の限定的な照合成功、`installed` が実体確認のみ、`missing` が実体なし、`incompatible` が固定値との不一致、`broken` が実体の不備、`unknown` が判定不能、`manual-required` が手動工程を要すること。導入結果は `success`、`skipped`、`blocked`、`failed`、`manual-required` に分ける。終了コードは0=完了、1=実行失敗、2=保留を含む未完了、3=事前条件/確認エラー。

## 現時点で自動導入を保留するもの

SliverはローカルSHA-256があっても公式release URLとの対応が未確定。Havocは本体・submoduleの基準コミットが不明で、保存済みスナップショットを自動適用できない。EmpireとBloodHound CEはimage digestが未固定。Pythonの8環境はLevel 2でwheel/SDist hashと解決条件がない。ライセンス付きGUIとWindows専用成果物も手動条件を残す。NetExecの1行パッチは、固定コミットの上流SHA-256と照合できるが、既存uv環境には自動再適用しない。

`c2/` の公式インターフェースを直接使う場合は、Sliver `./c2/Sliver/bin/sliver-server_darwin-arm64`（必要時に公式Client）、Havoc `./c2/Havoc/teamserver/havoc-teamserver server --profile <private-localhost-profile>` と `(cd c2/Havoc && ./client/Havoc)`、Empire `docker compose -f c2/empire/compose.yaml up -d` / `stop`。これらはインストーラーの操作ではない。Havoc元profileは全インターフェースbindのため、ローカル管理用には私用コピーを用意する。

## 失敗時

不一致や既存ファイルの発見時は上書きせず停止する。表示されたID、理由、固定版を確認し、`--audit` と `--dry-run --tool <id>` で再評価する。実導入の構造化記録はユーザー専用の `Library/Logs/RedTeam_Toolkit_for_Mac/installer.jsonl` にある。部分成功したツールは保持され、次回は検出してスキップされる。容量不足なら作業前に空き容量を確保する。Docker Volume、既存venv、Havoc/Sliverデータの自動削除・復元は行わない。

現在のリポジトリでは重要なソースやバイナリの一部がGit追跡外またはignore対象で、クローンだけでは全資産が揃わない。`--dry-run` の保留理由と [再現性の課題](reproducibility-gaps.md)を確認してから導入する。
