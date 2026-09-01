#!/usr/bin/env bash
# run_tests.sh —— 测试输出缓存 runner（用户 2026-09-01 想法）
#
# 问题：全量 unittest 250s+，经常为观察不同点（Ran/OK/FAILED/详情）重跑
# 同一命令——同一份输出观察多次，浪费。
# 方案：源码（被测代码+测试代码+wrapper+模板）内容指纹 + 命令参数 →
#   缓存 key。缓存命中且上次 OK → 直接输出缓存（0 秒）；否则重跑并存缓存。
# 安全规则：上次 FAILED 的缓存不可信（flaky/环境变化）→ 重跑确认。
#
# 用法：
#   ./tests/run_tests.sh                 # 全量（discover tests）
#   ./tests/run_tests.sh tests.test_viewer   # 单文件（参数参与指纹）
#   ./tests/run_tests.sh --force         # 强制重跑（忽略缓存）
# 输出与 `python3 -m unittest ...` 完全一致（tee 缓存 + stdout），
# 管道（grep 等）照常用。

set -u

HERE="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_DIR="${TEST_CACHE_DIR:-$HERE/tests/.cache}"
mkdir -p "$CACHE_DIR"

FORCE=0
ARGS=()
for a in "$@"; do
    if [ "$a" = "--force" ]; then
        FORCE=1
    else
        ARGS+=("$a")
    fi
done
if [ "${#ARGS[@]}" -eq 0 ]; then
    ARGS=(discover tests)
fi

# 源码指纹：被测代码 + 测试代码 + wrapper + 模板（内容 md5，mtime 变内容
# 不变不失效）。find 括号优先级 + 排除 .git。
FILES="$(cd "$HERE" && find . \( -name '*.py' -o -name '*.sh' -o -name '*.tpl' \) \
    -not -path './.git/*' -not -path './tests/.cache/*' | sort)"
SRC_HASH="$(echo "$FILES" | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1)"
ARG_HASH="$(echo "${ARGS[*]}" | md5sum | cut -d' ' -f1)"
CACHE="$CACHE_DIR/${SRC_HASH}_${ARG_HASH}.log"

cache_ok() {
    # 上次 OK（允许 expected failures）才可信
    grep -qE '^OK( \(expected failures=[0-9]+\))?$' "$CACHE"
}

if [ "$FORCE" -eq 1 ]; then
    echo "[run_tests] --force 强制重跑" >&2
elif [ -f "$CACHE" ] && cache_ok; then
    echo "[run_tests] 缓存命中（源码/参数未变，上次 OK）——直接输出缓存；--force 强制重跑" >&2
    cat "$CACHE"
    exit 0
elif [ -f "$CACHE" ]; then
    echo "[run_tests] 缓存存在但上次有错误——重跑确认（flaky/环境变化）" >&2
else
    echo "[run_tests] 无缓存或源码已变——运行测试并保存缓存" >&2
fi

cd "$HERE"
python3 -m unittest "${ARGS[@]}" 2>&1 | tee "$CACHE"
exit "${PIPESTATUS[0]}"
