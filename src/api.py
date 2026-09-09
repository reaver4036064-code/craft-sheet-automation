"""打板管理系统 API 封装。依赖 config。"""
import time
import requests
from config import BASE


def login(username, password):
    ts = int(time.time() * 1000)
    r = requests.post(f"{BASE}/colorimeter/index/login?time={ts}",
        json={"loginName": username, "password": password, "deviceCode": None, "loginType": "erp-pc"},
        headers={"Content-Type": "application/json"})
    return r.json()["data"]["token"]


def api_headers(token):
    return {"Content-Type": "application/json;charset=UTF-8", "token": token, "Accept": "application/json, text/plain, */*"}


def upload_image(token, path):
    with open(path, "rb") as f:
        r = requests.post(f"{BASE}/business/upload/img",
            files={"img": ("craft.jpg", f, "image/jpeg")}, headers={"token": token})
    d = r.json()
    if d.get("success"):
        return d["data"]["url"]
    raise Exception(f"Upload failed: {d}")


def get_labels(token):
    r = requests.post(f"{BASE}/business/markLabel/select", json={}, headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])


def get_fabrics(token):
    """Get all fabrics from the system for lookup"""
    r = requests.post(f"{BASE}/colorimeter/bFabric/selectFabricList", json={}, headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])


def get_customers(token):
    r = requests.get(f"{BASE}/business/customer/public", headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])


def get_user_list(token):
    """查询设计部用户列表，返回 [{userId, userName, ...}]。"""
    r = requests.get(f"{BASE}/dept/getUserList/name",
        params={"deptName": "设计部"}, headers=api_headers(token))
    data = r.json()
    if data.get("success"):
        return data.get("data", {}).get("items", [])
    return []
