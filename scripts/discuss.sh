#!/usr/bin/env bash
#
# pi-agents-helper wrapper（pi-meeting 的 human 通道版本）
#
# 用法：
#   ./scripts/discuss.sh --prepare "<问题>" [--background "<背景>"]
#   ./scripts/discuss.sh --start <spec目录>
#   ./scripts/discuss.sh --status <dir>
#   ./scripts/discuss.sh --wait <dir>
#   ./scripts/discuss.sh --cleanup <dir>
#   ./scripts/discuss.sh --view <dir> [--since <ref>]     # human-viewer 封装
#   ./scripts/discuss.sh --say <dir> "<文本>"              # human-sayer 封装
#
# 设计文档：docs/pi-helper-design.md（§5.1.2 主 pi 代理形态）
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"
START_DISCUSSION="$ROOT_DIR/start_discussion.py"
HUMAN_VIEWER="$ROOT_DIR/human_viewer.py"
HUMAN_SAYER="$ROOT_DIR/human_sayer.py"
SPEC_README_TPL="$ROOT_DIR/templates/spec-readme.md.tpl"

DEFAULT_AGENTS="a,b,c"
DEFAULT_MAX_MEETING=10
DEFAULT_MAX_RR=5

usage() {
    cat <<'USAGE_EOF'
用法:
  $0 --prepare "<问题>" [--background "<背景>"]
  $0 --start <spec目录>
  $0 --status <dir>
  $0 --wait <dir>
  $0 --cleanup <dir>
  $0 --view <dir> [--since <ref>]
  $0 --say <dir> "<文本>"

默认讨论参数:
  agents=a,b,c  max-meeting=10  max-rr=5

human 通道:
  --view: 增量查看讨论进展（--since 之后的新消息+状态；末尾输出 HEAD=<hash>，主 pi 记录作下轮 --since）
  --say:  插话（写一条 human 消息，agents 可见并可回应）
USAGE_EOF
}

fail() {
    echo "错误: $*" >&2
    exit 1
}

require_dir() {
    local dir="$1"
    [ -n "$dir" ] || fail "缺少目录参数"
    [ -d "$dir" ] || fail "目录不存在: $dir"
}

cmd_status() {
    local dir="$1"
    require_dir "$dir"
    "$PYTHON" "$START_DISCUSSION" --dir "$dir" --status
}

cmd_wait() {
    local dir="$1"
    require_dir "$dir"
    "$PYTHON" "$START_DISCUSSION" --dir "$dir" --wait
}

cmd_cleanup() {
    local dir="$1"
    require_dir "$dir"
    "$PYTHON" "$START_DISCUSSION" --dir "$dir" --cleanup
}

cmd_view() {
    local dir="$1" since=""
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --since)
                [ "$#" -ge 2 ] || fail "--since 需要一个值"
                since="$2"
                shift 2
                ;;
            *)
                fail "未知参数: $1（--view 只接受 --since）"
                ;;
        esac
    done
    require_dir "$dir"
    [ -d "$dir/repo.git" ] || fail "讨论不存在: $dir（无 repo.git）"
    if [ -n "$since" ]; then
        "$PYTHON" "$HUMAN_VIEWER" "$dir" --since "$since"
    else
        "$PYTHON" "$HUMAN_VIEWER" "$dir"
    fi
    # HEAD 游标（主 pi 记录作下轮 --since；无状态，不写游标文件——
    # 与 tmux --follow 的 .viewer-cursor 互不干扰）
    echo "HEAD=$(git -C "$dir/repo.git" rev-parse HEAD)"
}

cmd_say() {
    local dir="$1" text="${2:-}"
    require_dir "$dir"
    [ -d "$dir/work-human" ] || fail "讨论缺少 work-human: $dir"
    [ -n "$text" ] || fail "插话文本不能为空"
    "$PYTHON" "$HUMAN_SAYER" "$dir" "$text"
}

# 定位主 pi 的 session 文件：优先 PI_SESSION_FILE，否则用当前 cwd 编码路径查找
find_pi_session_file() {
    local session_file="${PI_SESSION_FILE:-}"
    if [ -n "$session_file" ] && [ -f "$session_file" ]; then
        echo "$session_file"
        return
    fi
    # cwd 编码：/root/book/sh -> --root-book-sh--
    local encoded
    encoded="--$(printf '%s' "$PWD" | sed 's|^/||; s|/|-|g')--"
    local session_dir="$HOME/.pi/agent/sessions/$encoded"
    ls -t "$session_dir"/*.jsonl 2>/dev/null | head -1
}

# 从主 pi session 文件读取最后一个 model_change / thinking_level_change
read_pi_model_thinking_from_session() {
    local session_file
    session_file="$(find_pi_session_file)"
    if [ -z "$session_file" ] || [ ! -f "$session_file" ]; then
        echo "|"
        return
    fi
    "$PYTHON" - "$session_file" <<'PYEOF'
import json, sys
model = ""
thinking = ""
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "model_change":
                provider = ev.get("provider", "")
                model_id = ev.get("modelId", "")
                if provider and model_id:
                    model = f"{provider}/{model_id}"
                elif model_id:
                    model = model_id
            elif ev.get("type") == "thinking_level_change":
                thinking = ev.get("thinkingLevel", "")
except Exception:
    pass
print(f"{model}|{thinking}")
PYEOF
}

# 读取主 pi 的 model/thinking（用户 2026-08-31：aft 不再替换 bash 后
# 环境变量可用且是当前生效值——优先环境变量，session 文件解析仅为兜底）
read_pi_model_thinking() {
    local provider="${PI_PROVIDER:-}"
    local model="${PI_MODEL:-}"
    local thinking="${PI_REASONING_LEVEL:-}"
    local full_model=""

    if [ -n "$provider" ] && [ -n "$model" ]; then
        full_model="$provider/$model"
    elif [ -n "$model" ]; then
        full_model="$model"
    fi

    # 兜底：环境变量缺失时解析 session 文件（旧路径，aft 替换 bash 时代的产物）
    if [ -z "$full_model" ] || [ -z "$thinking" ]; then
        local from_session
        from_session="$(read_pi_model_thinking_from_session)"
        local session_model="${from_session%%|*}"
        local session_thinking="${from_session##*|}"
        if [ -z "$full_model" ] && [ -n "$session_model" ]; then
            full_model="$session_model"
        fi
        if [ -z "$thinking" ] && [ -n "$session_thinking" ]; then
            thinking="$session_thinking"
        fi
    fi
    echo "$full_model|$thinking"
}

# agents 列表（DEFAULT_AGENTS 逗号分隔 → 行分隔写入 .order）
cmd_prepare() {
    local topic="" background=""
    if [ "$#" -lt 1 ]; then
        usage >&2
        exit 2
    fi
    topic="$1"
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --background)
                [ "$#" -ge 2 ] || fail "--background 需要一个值"
                background="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                fail "未知参数: $1（--prepare 只接受 <问题> 和 --background）"
                ;;
        esac
    done
    [ -n "$topic" ] || fail "问题不能为空"

    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    local spec_dir="$PWD/pi-agents-helper-spec-${stamp}"
    mkdir -p "$spec_dir/agents"

    # question.md
    cat > "$spec_dir/question.md" <<EOF
# question.md——说明行，不注入

# 讨论主题：$topic

## 初始立场（可选，每参与者一行）
- a: 立场
- b: 立场
- c: 立场

## 待回答的问题（可选）
- 问题
EOF

    # background.md
    if [ -n "$background" ]; then
        cat > "$spec_dir/background.md" <<EOF
# background.md——说明行，不注入

$background
EOF
    else
        cat > "$spec_dir/background.md" <<EOF
# background.md——说明行，不注入

EOF
    fi

    # models.md：延用主 pi 的 model/thinking，缺失则 default
    local mt
    mt="$(read_pi_model_thinking)"
    local pi_model="${mt%%|*}"
    local pi_thinking="${mt##*|}"
    {
        echo "# models.md——说明行，不注入"
        for agent in a b c; do
            if [ -n "$pi_model" ] && [ -n "$pi_thinking" ]; then
                echo "$agent: $pi_model, $pi_thinking"
            elif [ -n "$pi_model" ]; then
                echo "$agent: $pi_model"
            elif [ -n "$pi_thinking" ]; then
                echo "$agent: default, $pi_thinking"
            else
                echo "$agent: default"
            fi
        done
    } > "$spec_dir/models.md"

    # agents/*.md
    for agent in a b c; do
        cat > "$spec_dir/agents/$agent.md" <<EOF
# $agent.md——说明行，不注入

EOF
    done
    printf 'a\nb\nc\n' > "$spec_dir/agents/.order"

    # README
    if [ -f "$SPEC_README_TPL" ]; then
        cp "$SPEC_README_TPL" "$spec_dir/README.md"
    fi

    cat <<OUTPUT_EOF
已生成讨论 spec:
  $spec_dir

请查看/编辑该目录，补充背景、各 agent 视角等。
编辑完成后，告诉我"继续"，我会自动启动讨论。
OUTPUT_EOF
}

cmd_start() {
    local spec_dir="$1"
    require_dir "$spec_dir"
    [ -f "$spec_dir/question.md" ] || fail "spec 缺少 question.md: $spec_dir"

    local session_id="${PI_SESSION_ID:-}"
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    local dir_name="discuss"
    if [ -n "$session_id" ]; then
        dir_name="${dir_name}-${session_id}"
    fi
    dir_name="${dir_name}-${stamp}"
    local dir_path="$PWD/$dir_name"

    # 第 1 步：创建讨论环境（不启动）
    if ! "$PYTHON" "$START_DISCUSSION" --dir "$dir_path" --spec "$spec_dir" --max-meeting "$DEFAULT_MAX_MEETING" --max-rr "$DEFAULT_MAX_RR"; then
        fail "讨论环境创建失败，请查看上方输出"
    fi

    # 第 2 步：在每个 work 目录写入项目级 .pi/settings.json，禁用 magic-context 和 aft
    local agent
    for agent in a b c; do
        local workdir="$dir_path/work-$agent"
        if [ -d "$workdir" ]; then
            mkdir -p "$workdir/.pi"
            cat > "$workdir/.pi/settings.json" <<'SETTINGS_EOF'
{
  "packages": [
    { "source": "npm:@cortexkit/pi-magic-context", "autoload": false },
    { "source": "npm:@cortexkit/aft-pi", "autoload": false }
  ]
}
SETTINGS_EOF
        fi
    done

    # 临时 spec 已被消费，删除
    rm -rf "$spec_dir"

    # 第 3 步：启动已有环境
    if ! "$PYTHON" "$START_DISCUSSION" --dir "$dir_path" --skip-setup --start; then
        fail "讨论启动失败，请查看上方输出"
    fi

    cat <<OUTPUT_EOF
讨论已启动
目录: $dir_path
查看进展: $0 --view $dir_path
插话: $0 --say $dir_path "<文本>"
查看状态: $0 --status $dir_path
等待完成: $0 --wait $dir_path
清理: $0 --cleanup $dir_path

说明:
- human 通道：--view 增量查看（主 pi 记录末尾 HEAD 作下轮 --since）；
  --say 插话（agents 可见并可回应；已冻结 agent 不响应）
- 完成后 result.md 默认由 resultWriter=c 生成，位于 $dir_path/work-c/result.md
- 读取 result.md 后请执行 --cleanup 清理讨论目录
OUTPUT_EOF
}

if [ "$#" -ge 1 ]; then
    case "$1" in
        --prepare)
            shift
            cmd_prepare "$@"
            exit $?
            ;;
        --start)
            [ "$#" -ge 2 ] || fail "--start 需要 spec 目录参数"
            cmd_start "$2"
            exit $?
            ;;
        --status)
            [ "$#" -ge 2 ] || fail "--status 需要讨论目录参数"
            cmd_status "$2"
            exit $?
            ;;
        --wait)
            [ "$#" -ge 2 ] || fail "--wait 需要讨论目录参数"
            cmd_wait "$2"
            exit $?
            ;;
        --cleanup)
            [ "$#" -ge 2 ] || fail "--cleanup 需要讨论目录参数"
            cmd_cleanup "$2"
            exit $?
            ;;
        --view)
            [ "$#" -ge 2 ] || fail "--view 需要讨论目录参数"
            shift
            cmd_view "$@"
            exit $?
            ;;
        --say)
            [ "$#" -ge 3 ] || fail "--say 需要讨论目录和文本参数"
            cmd_say "$2" "$3"
            exit $?
            ;;
        -h|--help)
            usage
            exit 0
            ;;
    esac
fi

usage >&2
exit 2