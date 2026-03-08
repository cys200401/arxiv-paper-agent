#!/bin/bash
# 在 Conda 环境 arxiv 中安装 Turso CLI
# 用法：先执行 conda activate arxiv，再运行 ./install_turso_conda.sh

set -e
INSTALL_DIR="${CONDA_PREFIX:?请先执行: conda activate arxiv}/bin"
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP_DIR="$BIN_DIR/.tmp_turso"
mkdir -p "$TMP_DIR"

echo "将安装 Turso CLI 到: $INSTALL_DIR"
echo "正在下载 Turso (Darwin arm64) ..."
curl -sSfL "https://github.com/tursodatabase/homebrew-tap/releases/latest/download/homebrew-tap_Darwin_arm64.tar.gz" -o "$TMP_DIR/turso.tar.gz"
tar -xzf "$TMP_DIR/turso.tar.gz" -C "$TMP_DIR" turso
chmod +x "$TMP_DIR/turso"
cp "$TMP_DIR/turso" "$INSTALL_DIR/turso"
rm -rf "$TMP_DIR"
echo "安装完成。当前环境中可直接运行: turso --version"
turso --version
