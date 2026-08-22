"""ari web_api —— FastAPI 应用入口。

路由注册顺序很重要：接口路由必须全部注册在静态挂载之前。
`StaticFiles` 挂在 `/` 上会吞掉之后所有未匹配的路径，
所以它永远是最后一行。以后新增接口一律走 `/api/` 前缀。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

# 相对 __file__ 解析，不依赖进程的工作目录，
# 这样 systemd、pytest、本地 uvicorn 三种启动方式都指向同一个目录。
_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = _ROOT / "static"
PROTOTYPE_DIR = _ROOT / "prototype"

app = FastAPI(title="ari web_api")


@app.get("/health")
def health() -> dict[str, str]:
    """供 systemd、Nginx 与外部探活使用的健康检查。"""
    return {"status": "ok"}


@app.get("/prototype", include_in_schema=False)
def prototype_root_redirect() -> RedirectResponse:
    """补上缺失的尾斜杠。

    根挂载会先匹配掉不带斜杠的 `/prototype`，让 Starlette 的自动补斜杠
    没机会生效，结果是 404。这条路由注册在挂载之前，把它抢回来。
    """
    return RedirectResponse("/prototype/")


# —— 接口路由写在这条线以上 ——

# 在线原型。必须排在根挂载之前：根挂载会吞掉它之后的所有未匹配路径。
app.mount("/prototype", StaticFiles(directory=PROTOTYPE_DIR, html=True), name="prototype")

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
