# NetExec `--version` 終了コード修正

- 対象: `nxc/cli.py`、uv tool `netexec` v1.5.1+0.c7dc286b、Python 3.12.12。
- 上流: `https://github.com/Pennyw0rth/NetExec.git`、`direct_url.json` が示す commit `c7dc286ba65daf10402cdc470e531b84e6d3d911`、requested revision `v1.5.1`。Git 管理された checkout の現在 HEAD を確認したという意味ではない。
- 上流ファイル SHA-256: `596c98a6aa6266f0d516912f3b1afa631a7b526284cc6218897a395e5b61c1e2`。
- 現行 uv 環境の同ファイル SHA-256: `f30ea3cf88927895a9aaf656a05a7aac016c18223bb47b75e93154b7470e9218`。
- 差分: `if args.version:` 分岐の `sys.exit(1)` を `sys.exit(0)` に変更する **1行のみ**。固定コミットの上流 raw file と現行ファイルの完全 diff で確認した。
- 動作: 現行の `nxc --version` は v1.5.1 を表示し、終了コード 0。認証や対象接続は行っていない。

`version-exit-code.patch` はこの固定コミットの上流ファイルに対する unified diff。将来適用する前に、取得した `nxc/cli.py` の SHA-256 が上記の上流値と一致し、patch が未適用であることを確認する。適用後は現行ファイルの SHA-256 と `nxc --version` の終了コード 0 を確認する。既に現行 hash の場合は再適用しない。別 revision や異なる hash には自動適用しない。

今回の検証は固定コミットの raw file を一時領域に取得して差分を照合する方式。既存 uv 環境のファイルや package は変更していない。クリーンな uv tool 再インストールまで含む end-to-end 検証は未実施。
