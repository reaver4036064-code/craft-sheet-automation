"""身份管理：持久化到 .identity.json，模块状态 USER_REALNAME/USER_DESIGNER_ID/USERNAME/PASSWORD。依赖 config+api。"""
import json
import os
from config import SCRIPT_DIR
import api

IDENTITY_FILE = SCRIPT_DIR / ".identity.json"

USERNAME = os.getenv("MC_USERNAME", "")
PASSWORD = os.getenv("MC_PASSWORD", "")
USER_REALNAME = None
USER_DESIGNER_ID = None


def load_identity():
    if IDENTITY_FILE.exists():
        try:
            return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_identity(data):
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_identity():
    global USER_REALNAME, USER_DESIGNER_ID, USERNAME, PASSWORD
    saved = load_identity()
    if saved:
        USER_REALNAME = saved.get("realname")
        USER_DESIGNER_ID = saved.get("designer_id")
        USERNAME = saved.get("username", USERNAME)
        PASSWORD = saved.get("password", PASSWORD)
        if USER_REALNAME and USER_DESIGNER_ID:
            return True
    # First run: ask
    print("\n" + "="*50)
    print("首次使用 — 请提供身份信息（仅需一次）")
    print("="*50)
    try:
        name = input("请输入您的真实姓名: ").strip()
        sys_user = input("请输入嘉谦系统账号: ").strip()
        sys_pass = input("请输入嘉谦系统密码: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("取消")
        return False
    if not name or not sys_user or not sys_pass:
        print("姓名、账号、密码不能为空")
        return False
    USERNAME = sys_user
    PASSWORD = sys_pass
    try:
        token = api.login(USERNAME, PASSWORD)
    except Exception:
        print(f"账号 \"{sys_user}\" 登录失败")
        return False
    # Lookup userId
    try:
        for u in api.get_user_list(token):
            if u.get("userName") == name:
                USER_REALNAME = name
                USER_DESIGNER_ID = str(u["userId"])
                save_identity({"realname": name, "designer_id": str(u["userId"]),
                    "username": USERNAME, "password": PASSWORD})
                print(f"身份验证通过: {name} (ID={USER_DESIGNER_ID})")
                return True
    except Exception as e:
        print(f"查询失败: {e}")
    print(f"设计师 \"{name}\" 未在系统中注册，请联系管理员")
    return False
