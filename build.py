"""
店小秘排单号自动填写工具 - 打包脚本

使用方法：
    pip install pyinstaller
    python build.py

打包完成后，exe 文件在 dist/店小秘排单工具/ 目录下
"""
import os
import sys
import shutil
import subprocess


def build():
    """使用 PyInstaller 打包为单文件 exe"""

    # 确保在项目目录
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    # 清理旧的构建文件
    for d in ["build", "dist", "*.spec"]:
        if os.path.exists(d) and not d.startswith("*"):
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
    for f in os.listdir(project_dir):
        if f.endswith(".spec"):
            os.remove(f)

    # 打包命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",              # 单 exe 文件
        "--windowed",             # 无控制台窗口
        "--name", "店小秘排单工具",
        "--icon", "NONE",          # 无图标，可替换为本地 .ico 文件
        "--add-data", f"requirements.txt{os.pathsep}.",
        "--clean",
        "--noconfirm",
        "main.py",
    ]

    print("=" * 60)
    print("  店小秘排单号自动填写工具 - 打包")
    print("=" * 60)
    print(f"  Python: {sys.executable}")
    print(f"  输出: dist/店小秘排单工具.exe")
    print("=" * 60)
    print()

    # 执行打包
    result = subprocess.run(cmd, cwd=project_dir)

    if result.returncode == 0:
        print()
        print("=" * 60)
        print("  ✅ 打包成功！")
        print(f"  📦 exe 文件: {os.path.join(project_dir, 'dist', '店小秘排单工具.exe')}")
        print()
        print("  使用方法：")
        print("    1. 将 exe 文件复制到任意目录")
        print("    2. 确保电脑已安装 Chrome 浏览器")
        print("    3. 双击运行")
        print()
        print("  注意：首次运行时，Windows 可能会弹出安全提示，")
        print("       点击「更多信息」→「仍要运行」即可")
        print("=" * 60)
    else:
        print()
        print("❌ 打包失败，请检查上方错误信息")
        sys.exit(1)


if __name__ == "__main__":
    build()
