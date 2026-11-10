# 配布構成

GitHubのルートREADMEから`install/`へ進む。インストーラー本体、Manifest、8個のPythonロック、公開可能な最小パッチ・スナップショット、テスト、文書、Empire Composeと値を含まない設定例を`install/`に置く。GitHub Actionsの有効なworkflowだけはルート`.github/workflows/`に置く。Git indexの一覧は`publication-files.txt`を正本とする。

```sh
git clone <repository-url>
cd RedTeam_Toolkit_for_Mac/install
./install.sh --help
./install.sh --list
./install.sh --dry-run
```

既存ツールやユーザーデータはリポジトリの`install/`外、または各公式の配置先に保持する。venv、C2ソース・バイナリ・証明書、Docker Volume、ログ、個人設定、大容量の外部OSS一式は公開対象外。Sliverは公式配布URLとSHA-256の対応が確定するまで自動取得を保留する。Havocは基準コミット未確定で、スナップショットを自動適用しない。NetExecは固定コミット用の最小パッチのみを保存する。Havoc・toml11のスナップショットには各ライセンス文書を添付する。プロジェクト独自コードのライセンスは所有者の最終判断待ち。

ローカル実体のSHA-256を公式配布物の真正性の証拠と混同しない。公開前にはGit indexの秘密情報検査、第三者OSSの再配布条件、相対リンク、CI結果を再確認する。GitHubからのクローン後に109ツールを完全自動再現できる状態にはまだ達していない。
