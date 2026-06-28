"""
面料库查询工具
从打板系统 API 查询面料信息：编号匹配、颜色列表、成分/克重/幅宽/供应商自动填充
"""

import requests
import time
from typing import Dict, List, Optional


def login_and_get_token(base_url: str, username: str, password: str) -> str:
    ts = int(time.time() * 1000)
    r = requests.post(
        f"{base_url}/colorimeter/index/login?time={ts}",
        json={"loginName": username, "password": password,
              "deviceCode": None, "loginType": "erp-pc"},
        headers={"Content-Type": "application/json"})
    return r.json()["data"]["token"]


def get_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "token": token,
        "Accept": "application/json, text/plain, */*"
    }


def fetch_fabric_library(base_url: str, token: str) -> List[Dict]:
    """获取完整面料库"""
    r = requests.post(
        f"{base_url}/colorimeter/bFabric/selectFabricList",
        json={}, headers=get_headers(token))
    return r.json().get("data", {}).get("list", [])


def find_fabric(product_no: str, library: List[Dict]) -> Optional[Dict]:
    """按面料编号(productNo)搜索面料，返回匹配项或None"""
    # 模糊匹配：包含关系
    for f in library:
        pn = str(f.get("productNo", ""))
        if product_no.upper() in pn.upper() or pn.upper() in product_no.upper():
            return f
    return None


def format_fabric_info(fabric: Dict) -> str:
    """格式化面料信息供对话展示"""
    colors = fabric.get("colorTypeVOS", [])
    color_str = ", ".join([f"{c['color']}({c['colorName']})" for c in colors[:10]])
    if len(colors) > 10:
        color_str += f"... 共{len(colors)}色"
    return (
        f"编号: {fabric['productNo']}\n"
        f"成分: {fabric.get('component', '-')}\n"
        f"幅宽: {fabric.get('buffon', '-')}cm\n"
        f"克重: {fabric.get('grem', '-')}\n"
        f"供应商: {fabric.get('supName', '-')}\n"
        f"可选色: {color_str}"
    )


def fetch_aux_library(base_url: str, token: str) -> List[Dict]:
    """获取辅料库"""
    r = requests.post(
        f"{base_url}/colorimeter/bAuxiliary/selectAuxiliaryList",
        json={}, headers=get_headers(token))
    return r.json().get("data", {}).get("list", [])


def fetch_bworks(base_url: str, token: str) -> Dict[int, List[Dict]]:
    """获取三类工艺：0=印花, 1=洗水, 2=车缝"""
    result = {}
    for btype in [0, 1, 2]:
        r = requests.post(
            f"{base_url}/business/bWork/selectBWork?type={btype}",
            json={}, headers=get_headers(token))
        result[btype] = r.json().get("data", {}).get("list", [])
    return result


def build_fabric_payload_item(fabric: Dict, color: str, color_name: str,
                               cloth_type: str, thread: str, cg_by: str,
                               sup_name: str = "") -> Dict:
    """根据面料库数据构建 insertDesign fabricList 项"""
    return {
        "productNo": fabric.get("productNo", ""),
        "color": color,
        "colorName": color_name,
        "buffon": str(fabric.get("buffon", "")),
        "grem": str(fabric.get("grem", "")),
        "supName": sup_name or fabric.get("supName", ""),
        "component": fabric.get("component", ""),
        "productName": fabric.get("productName", "") or "",
        "arrivedTime": "",
        "thread": thread,
        "isUsed": "0",
        "price": 0,
        "clothType": cloth_type,
        "cgBy": cg_by,
    }
