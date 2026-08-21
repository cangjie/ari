"""web_api 的最小验收测试。

只覆盖服务端职责：健康检查可用、静态页面被正确挂载。
页面里的 Geolocation 行为由浏览器提供，不在这里断言。
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_serves_static_index():
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>" in response.text


def test_static_mount_does_not_shadow_api_routes():
    """静态目录挂在 / 上，但注册在后，不能把 /health 吃掉。"""
    assert client.get("/health").status_code == 200


def test_missing_static_file_returns_404():
    assert client.get("/no-such-page.html").status_code == 404
