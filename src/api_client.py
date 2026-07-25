"""
工艺单自动上传 - API 客户端
支持沙箱/正式环境切换（通过 src/.mode 文件控制）
"""

import os
import time
import json
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path

def _load_mode():
    mode_path = Path(__file__).resolve().parent / ".mode"
    if mode_path.exists():
        return mode_path.read_text(encoding="utf-8").strip()
    return "production"

_URLS = {
    "sandbox":    {"api": "https://mctwo.fsjqfz.xyz/makeCloth", "web": "https://mctwo.fsjqfz.xyz"},
    "production": {"api": "https://mc.fsjqfz.xyz/makeCloth",    "web": "https://mc.fsjqfz.xyz"},
}
_MODE = _load_mode()
_DEFAULT_API = _URLS[_MODE]["api"]
_DEFAULT_WEB = _URLS[_MODE]["web"]


class MCAPIClient:
    """打板管理系统 API 客户端"""

    def __init__(self, base_url: str, web_url: str):
        self.base_url = base_url.rstrip("/")
        self.web_url = web_url.rstrip("/")
        self.token: Optional[str] = None
        self.session = requests.Session()

    # ========== 认证 ==========

    def login(self, username: str, password: str,
              login_type: str = "erp-pc") -> bool:
        """登录获取 JWT Token"""
        ts = int(time.time() * 1000)
        resp = self.session.post(
            f"{self.base_url}/colorimeter/index/login?time={ts}",
            json={
                "loginName": username,
                "password": password,
                "deviceCode": None,
                "loginType": login_type,
            },
            headers={"Content-Type": "application/json"}
        )
        data = resp.json()
        if data.get("success"):
            self.token = data["data"]["token"]
            return True
        return False

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "token": self.token or "",
            "Accept": "application/json, text/plain, */*"
        }

    # ========== 图片上传 ==========

    def upload_image(self, image_path: str) -> Optional[str]:
        """上传工艺单图片 → 返回 OSS URL"""
        img_endpoint = os.getenv("MC_IMAGE_UPLOAD_URL", "/business/upload/img")
        with open(image_path, "rb") as f:
            resp = self.session.post(
                f"{self.base_url}{img_endpoint}",
                files={"img": f},
                headers={"token": self.token or ""}
            )
        data = resp.json()
        if data.get("success"):
            return data["data"]["url"]
        return None

    # ========== 设计单创建 ==========

    def insert_design(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建设计单（板单新增）"""
        endpoint = os.getenv("MC_DESIGN_INSERT_URL", "/business/design/insertDesign")
        resp = self.session.post(
            f"{self.base_url}{endpoint}",
            json=payload,
            headers=self._headers()
        )
        return resp.json()

    def update_design(self, design_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """编辑设计单（板单修改）"""
        payload["id"] = design_id
        endpoint = os.getenv("MC_DESIGN_UPDATE_URL", "/business/design/updateDesign")
        resp = self.session.post(
            f"{self.base_url}{endpoint}",
            json=payload,
            headers=self._headers()
        )
        return resp.json()

    def search_designs(self, user_id: int, item_num: str = "",
                       page: int = 1, limit: int = 20) -> List[Dict]:
        """查询设计单列表"""
        resp = self.session.post(
            f"{self.base_url}/business/design/selectList",
            json={
                "current": page, "limit": limit,
                "code": "", "itemNum": item_num,
                "customerName": [], "vNumber": "", "userId": user_id
            },
            headers=self._headers()
        )
        data = resp.json()
        return data.get("data", {}).get("list", []) if data.get("success") else []

    def get_design_detail(self, design_id: int) -> Optional[Dict]:
        """获取设计单完整详情（含面料/辅料/图片等）"""
        resp = self.session.get(
            f"{self.base_url}/business/design/selectById",
            params={"id": design_id},
            headers=self._headers()
        )
        data = resp.json()
        if data.get("success"):
            return data.get("data", {}).get("info", {})
        return None

    # ========== 查询接口 ==========

    def get_customers(self) -> List[Dict]:
        """查询客户列表"""
        endpoint = os.getenv("MC_CUSTOMER_LIST_URL", "/business/customer/public")
        resp = self.session.get(
            f"{self.base_url}{endpoint}",
            headers=self._headers()
        )
        data = resp.json()
        return data.get("data", {}).get("list", []) if data.get("success") else []

    def get_designers(self, dept_name: str = "设计部") -> List[Dict]:
        """查询设计师列表"""
        endpoint = os.getenv("MC_DESIGNER_LIST_URL", "/dept/getUserList/name")
        resp = self.session.get(
            f"{self.base_url}{endpoint}",
            params={"deptName": dept_name},
            headers=self._headers()
        )
        data = resp.json()
        return data.get("data", []) if data.get("success") else []

    def get_fabric_list(self) -> List[Dict]:
        """查询面料列表"""
        resp = self.session.post(
            f"{self.base_url}/colorimeter/bFabric/selectFabricList",
            json={},
            headers=self._headers()
        )
        return resp.json().get("data", {}).get("list", [])

    def get_mark_labels(self) -> List[Dict]:
        """查询唛头资料"""
        resp = self.session.post(
            f"{self.base_url}/business/markLabel/select",
            json={},
            headers=self._headers()
        )
        return resp.json().get("data", {}).get("list", [])

    def get_data_dict(self, user_id: int = 74) -> Dict:
        """查询数据字典（下拉选项）"""
        resp = self.session.post(
            f"{self.base_url}/colorimeter/permission/getDataDictionarys/{user_id}",
            json={},
            headers=self._headers()
        )
        return resp.json().get("data", {}).get("dataDictionarys", {})

    def close(self):
        self.session.close()


def load_config() -> Dict[str, str]:
    return {
        "api_base": os.getenv("MC_API_BASE_URL", _DEFAULT_API),
        "web_base": os.getenv("MC_WEB_BASE_URL", _DEFAULT_WEB),
        "username": os.getenv("MC_USERNAME", ""),
        "password": os.getenv("MC_PASSWORD", ""),
        "login_type": os.getenv("MC_LOGIN_TYPE", "erp-pc"),
    }
