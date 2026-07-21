#!/bin/bash
# UZI-Skill 一键安装脚本
# 用法: bash <(curl -fsSL https://raw.githubusercontent.com/wbh604/UZI-Skill/main/setup.sh)

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 游资（UZI）Skills · 安装中..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "❌ 未找到 Python，请先安装 Python 3.9+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "✓ Python: $($PYTHON --version)"

# 检查 git
if ! command -v git &>/dev/null; then
    echo "❌ 未找到 git"
    exit 1
fi

# 克隆（如果不在仓库内）
if [ ! -f "run.py" ]; then
    if [ -d "UZI-Skill" ]; then
        echo "✓ UZI-Skill 目录已存在，更新中..."
        cd UZI-Skill && git pull
    else
        echo "⏬ 克隆仓库..."
        git clone https://github.com/wbh604/UZI-Skill.git
        cd UZI-Skill
    fi
else
    echo "✓ 已在仓库目录中"
fi

# 安装依赖 — 先试默认 pypi，挂了就自动切国内镜像（大陆网络环境友好）
echo "📦 安装 Python 依赖..."

PIP_MIRRORS=(
    ""  # 默认 pypi.org（空字符串代表不指定 -i，走默认）
    "https://pypi.tuna.tsinghua.edu.cn/simple"
    "https://mirrors.aliyun.com/pypi/simple/"
    "https://pypi.mirrors.ustc.edu.cn/simple/"
)

install_deps() {
    local mirror="$1"
    if [ -z "$mirror" ]; then
        $PYTHON -m pip install -r requirements.txt -q 2>/dev/null
    else
        local host
        host=$(echo "$mirror" | awk -F/ '{print $3}')
        $PYTHON -m pip install -r requirements.txt -q \
            --index-url "$mirror" \
            --trusted-host "$host" 2>/dev/null
    fi
}

SUCCESS=0
for mirror in "${PIP_MIRRORS[@]}"; do
    if [ -z "$mirror" ]; then
        echo "   [1] 尝试默认 pypi.org ..."
    else
        echo "   [+] 尝试镜像 $mirror ..."
    fi
    if install_deps "$mirror"; then
        SUCCESS=1
        [ -z "$mirror" ] && echo "   ✓ 安装成功（默认 pypi）" || echo "   ✓ 安装成功（via $mirror）"
        break
    fi
done

if [ "$SUCCESS" -eq 0 ]; then
    echo "   ❌ 所有源都失败。手动试："
    echo "      pip install -r requirements.txt \\"
    echo "          -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
fi

# v2.6 · 确保 hooks 脚本有可执行权限（论坛报告 macOS Claude plugin 不能执行）
if [ -d "hooks" ]; then
    chmod +x hooks/session-start hooks/run-hook.cmd 2>/dev/null
    echo "✓ hooks 脚本可执行权限已设置"
fi

# 验证
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 安装完成！"
echo ""
echo "用法:"
echo "  python run.py 贵州茅台           # 分析 A 股"
echo "  python run.py AAPL              # 分析美股"
echo "  python run.py 00700.HK          # 分析港股"
echo "  python run.py 600519.SH --remote # 生成公网链接"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
