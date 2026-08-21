"""ari web_api —— FastAPI 应用入口。

路由注册顺序很重要：接口路由必须全部注册在静态挂载之前。
`StaticFiles` 挂在 `/` 上会吞掉之后所有未匹配的路径，
所以它永远是最后一行。以后新增接口一律走 `/api/` 前缀。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 相对 __file__ 解析，不依赖进程的工作目录，
# 这样 systemd、pytest、本地 uvicorn 三种启动方式都指向同一个目录。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="ari web_api")


@app.get("/health")
def health() -> dict[str, str]:
    """供 systemd、Nginx 与外部探活使用的健康检查。"""
    return {"status": "ok"}


# —— 接口路由写在这条线以上 ——

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
