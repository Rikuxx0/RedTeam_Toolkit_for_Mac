# Havoc macOS ARM64 修正の保存

**保存形式はスナップショットであり、適用可能なパッチではない。** `c2/Havoc/` と `client/external/{json,spdlog,toml}` に個別の Git metadata がなく、現在の本体・サブモジュールの上流 commit を確定できない。root repository に `git -C c2/Havoc` が所属することは、Havoc 独自の履歴があることを意味しない。過去の `c84f775...` 記録は候補としてだけ扱う。

## 保存物と根拠

`snapshots/` は現在の `client/CMakeLists.txt`、toml11 の `exception.hpp`、`serializer.hpp` をバイト単位でコピーした。ビルド成果物、profile、DB、CMake cache、秘密情報はコピーしていない。各 SHA-256 と、JSON/spdlog/toml tree の内容 fingerprint は `source-fingerprints.yaml` にある。サブモジュールの configured URL は `.gitmodules` から取得した候補であり、現在の各 tree がその URL のどの commit かは不明。Git metadata がないため「未コミット差分なし」と判定できない。

現在の `client/CMakeLists.txt` は C++17、`string(APPEND CMAKE_CXX_FLAGS " -fpermissive")`、`external/spdlog/include`、`external/json/include`、`external/toml` の include paths を含む。過去記録の候補 commit `c84f7755a8b1c0f737576bdd3a0e982a296012f1` にある公式 `client/CMakeLists.txt` と比較すると、C++20→17 と flags の代入→追記の2行だけが異なった。**これはファイル単位の比較であり、現在の Havoc tree 全体の基準 commit を確定しない。** include paths は比較先にもあり、今回の比較からローカル変更とは認定しない。

toml11 の `exception.hpp` は `_GNU_SOURCE` 分岐に `!defined(__APPLE__)` を加え、`strerror_r` の GNU 版と POSIX 版の戻り値型を分ける実装を含む。`serializer.hpp` にも `__APPLE__` 分岐がある。toml11 の CMake は project version `3.7.1` を表示するが、公式 `v3.7.1` の `exception.hpp` とは多数の行が異なるため、そのタグを現在の submodule commit と見なせない。両ファイルの何行がローカル修正かは未確定であり、個別 patch に切り出していない。

## ビルド環境と保護範囲

既存 Teamserver/GUI は arm64 Mach-O。Go module と sum は存在する。Qt5 5.15.19、MinGW-w64 14.0.0_3 の x86/x64 cross compiler は arm64 Mach-O として確認した。既存 CMake cache は旧トップレベル `Havoc/client` を source path として記録し、Python 3.15 の interpreter/include/library を参照する。現在の source path は `c2/Havoc/client` であり、cache は再現手順に流用できない。cache 自体は個人パスを含むためスナップショットに含めない。元 profile の管理 bind は全インターフェースで、compiler paths は存在しない付属 cross compiler を指す。profile は変更していない。

## 将来パッチにする条件

1. 現在の Havoc 本体・各 submodule tree を、取得元の固定 commit と内容 hash で同定する。
2. その clean tree と本スナップショットを比較し、macOS 修正だけを抽出する。上流側に含まれる変更をローカル patch として二重保存しない。
3. clean tree に対する patch の構文・適用・出力 hash を隔離領域で検証する。
4. GUI と Teamserver の無害な build/起動確認は別の承認済み検証として扱う。既存 source、profile、DB、バイナリを上書きしない。

現時点では **CMake/toml11 のスナップショットを installer で自動適用しない**。`source-fingerprints.yaml` と現行ファイルの hash 一致は、この時点のローカル修正を失わず保存できたことだけを示す。
