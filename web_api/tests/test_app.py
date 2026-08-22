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

def test_prototype_index_is_served():
    """原型目录挂在 /prototype 下，目录根出 index.html。"""
    response = client.head("/prototype/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_prototype_h5_is_served():
    response = client.head("/prototype/h5.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_prototype_mount_precedes_root_mount():
    """/prototype 必须注册在根挂载之前，否则会被根挂载吞掉。

    根挂载下并没有 prototype/ 这个子目录，所以只要这条过了，
    就说明请求确实落在了 /prototype 挂载上。
    """
    assert client.head("/prototype/h5.html").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200


def test_prototype_missing_file_returns_404():
    assert client.head("/prototype/no-such-file.html").status_code == 404


def test_prototype_without_trailing_slash_redirects():
    """不带尾斜杠时会被根挂载抢走并 404，因此需要一条显式跳转。"""
    response = client.get("/prototype", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/prototype/"
