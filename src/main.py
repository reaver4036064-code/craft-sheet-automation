"""
工艺单自动上传 - 主入口
流程：WorkBuddy 对话填 Excel → 读取 Excel → 登录沙箱 → 上传图片 → 提交
Usage: python main.py <image1.jpg> [image2.jpg ...]
"""

import sys
import json
from submit_excel import submit


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <image1.jpg> [image2.jpg ...]")
        sys.exit(1)

    result = submit(sys.argv[1:])
    print(json.dumps(result, ensure_ascii=False, indent=2))
