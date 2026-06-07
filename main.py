"""
店小秘排单号自动填写工具 - 入口文件

运行方式：
    python main.py

打包方法：
    python build.py
"""
import sys
import os

# 确保当前目录在路径中（支持打包后的exe）
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

from gui import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
