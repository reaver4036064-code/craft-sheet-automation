# -*- coding: utf-8 -*-
"""重建 WorkBuddy Skill 分发包 craft-sheet-automation.zip。

用途：仓库代码/SKILL.md 改动后，必须重新打包，否则安装端仍运行旧版。
      本脚本显式写入条目（不用通配），并在打包后自校验，防止漏文件/混入旧模块。

用法：
    python scripts/build_skill_zip.py

退出码：0=成功且全部校验通过；1=校验失败（此时不要分发该 zip）。
"""
import hashlib
import os
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ZIP_PATH = REPO / "craft-sheet-automation.zip"
PREFIX = "craft-sheet-automation/"

# 分发包内容（相对仓库根的路径）
SRC_MODULES = [
    "config.py", "identity.py", "api.py", "matcher.py", "parsers.py",
    "excel_parser.py", "validator.py", "submitter.py", "submit_excel.py",
]
ENTRIES = [
    "SKILL.md",
    "README.md",
    "assets/form.html",
    "config/成衣工艺单_设计师填表模板_v7.xlsx",
] + ["src/" + m for m in SRC_MODULES]

# 绝不允许出现在分发包里的东西
FORBIDDEN = [
    "api_client.py", "field_mapper.py", "main.py", "customer_matcher.py",
    "excel_writer.py", "fabric_lookup.py",
    ".mode", ".identity.json", "test_data.json", "__pycache__",
]


def build():
    missing = [e for e in ENTRIES if not (REPO / e).exists()]
    if missing:
        print("缺少源文件，无法打包：")
        for m in missing:
            print("  -", m)
        return False

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in ENTRIES:
            z.write(REPO / rel, PREFIX + rel)

    with zipfile.ZipFile(ZIP_PATH) as z:
        names = z.namelist()
        skill = z.read(PREFIX + "SKILL.md").decode("utf-8")
        parser = z.read(PREFIX + "src/excel_parser.py").decode("utf-8")

    def md5(text):
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    checks = [
        ("条目数为 %d + 1" % len(ENTRIES), len(names) == len(ENTRIES)),
        ("SKILL.md 含「铁律」", "铁律" in skill),
        ("SKILL.md 含「严禁读图」", "严禁读图" in skill),
        ("SKILL.md name=craft-sheet-automation", "name: craft-sheet-automation" in skill),
        ("SKILL.md 无硬编码绝对路径", "F:\\WORKBUDDY" not in skill),
        ("内容无被禁文件", not any(f in n for n in names for f in FORBIDDEN)),
        ("src 恰好 9 个 .py", sorted(
            n[len(PREFIX) + 4:] for n in names if n.startswith(PREFIX + "src/")
        ) == sorted(SRC_MODULES)),
        ("zip 内 excel_parser.py 与仓库一致",
         md5(parser) == md5((REPO / "src/excel_parser.py").read_text(encoding="utf-8"))),
    ]

    print("打包完成：%s（%d 字节，%d 条目）" % (ZIP_PATH.name, ZIP_PATH.stat().st_size, len(names)))
    for rel in ENTRIES:
        print("  %8d  %s" % ((REPO / rel).stat().st_size, rel))

    ok = True
    for label, passed in checks:
        print(("  [OK]   " if passed else "  [FAIL] ") + label)
        ok = ok and passed
    if not ok:
        print("\n校验未通过 —— 请勿分发该 zip。")
    return ok


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
