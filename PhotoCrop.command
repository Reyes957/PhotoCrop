#!/bin/bash
# PhotoCrop — 双击启动
# 双击此文件即可打开 PhotoCrop GUI

cd "$(dirname "$0")"

echo "=========================================="
echo "  PhotoCrop 启动中..."
echo "=========================================="

# 检查 python3
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到 python3，请先安装 Python"
    read -p "按回车键退出..."
    exit 1
fi

# 检查并安装依赖
echo "检查依赖..."
python3 -c "import PySide6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装 PySide6（首次需要，请耐心等待）..."
    pip3 install PySide6 --user
fi

python3 -c "import fitz" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装 PyMuPDF..."
    pip3 install PyMuPDF --user
fi

python3 -c "import scipy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装 scipy..."
    pip3 install scipy --user
fi

echo "依赖检查完成"
echo ""

# 启动 GUI（不预加载文件，让用户自己选择）
echo "启动 PhotoCrop..."
# 抑制 macOS 上 Qt keymapper 警告
export QT_LOGGING_RULES="${QT_LOGGING_RULES};qt.qpa.keymapper=false"
python3 -m photocrop.main --gui

# 如果出错，暂停显示错误
if [ $? -ne 0 ]; then
    echo ""
    echo "启动失败，请查看上方错误信息"
    read -p "按回车键退出..."
fi
