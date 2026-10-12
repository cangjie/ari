"""ari web_api —— FastAPI 应用入口。

路由注册顺序很重要：接口路由必须全部注册在静态挂载之前。
`StaticFiles` 挂在 `/` 上会吞掉之后所有未匹配的路径，
所以它永远是最后一行。以后新增接口一律走 `/api/` 前缀。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import tour_qa

# 相对 __file__ 解析，不依赖进程的工作目录，
# 这样 systemd、pytest、本地 uvicorn 三种启动方式都指向同一个目录。
_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = _ROOT / "static"
PROTOTYPE_DIR = _ROOT / "prototype"
TOUR_DIR = _ROOT / "tour"

app = FastAPI(title="ari web_api")


@app.get("/health")
def health() -> dict[str, str]:
    """供 systemd、Nginx 与外部探活使用的健康检查。"""
    return {"status": "ok"}


# 导览站的游客互动。线上由 tour.snowmeet.top 的 Nginx 把 /api/ 反代到这里
app.include_router(tour_qa.router)
app.add_exception_handler(tour_qa.QaError, tour_qa.qa_error_handler)


@app.get("/prototype", include_in_schema=False)
def prototype_root_redirect() -> RedirectResponse:
    """补上缺失的尾斜杠。

    根挂载会先匹配掉不带斜杠的 `/prototype`，让 Starlette 的自动补斜杠
    没机会生效，结果是 404。这条路由注册在挂载之前，把它抢回来。
    """
    return RedirectResponse("/prototype/")


@app.get("/tour", include_in_schema=False)
def tour_root_redirect() -> RedirectResponse:
    """同上：不带尾斜杠的 `/tour` 会被根挂载抢走。"""
    return RedirectResponse("/tour/")


# —— 接口路由写在这条线以上 ——

# 在线原型。必须排在根挂载之前：根挂载会吞掉它之后的所有未匹配路径。
app.mount("/prototype", StaticFiles(directory=PROTOTYPE_DIR, html=True), name="prototype")

# 导览站。线上它由 Nginx 以 tour.snowmeet.top 直接提供，不走这里；
# 这条挂载是给本地联调用的 —— 一个端口同时出页面和 /api/tour/ 接口。
app.mount("/tour", StaticFiles(directory=TOUR_DIR, html=True), name="tour")

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
