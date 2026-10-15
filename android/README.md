# Ari Travel Android

原生 Kotlin / Views 外壳，复用 `web_api/tour`。本轮是文字版陪伴功能：地图、路线、景点介绍、公开问答、卫星定位、后台到站通知、悬浮导览员、设置与权限引导。

已按 2026-10-14 的最新取舍移除语音输入、语音唤醒和语音输出；没有麦克风权限。
悬浮窗问答复用现有公开接口，提交按钮前明确提示可能对所有游客公开；不增加私密接口。
导览员目前使用“瑞 / 爱”文字头像，形象素材后续可替换，切换共用同一套状态和交互。

**2026-10-14交付为代码架构。2026-10-15在Mac上按新增宛平城的要求继续标准构建与自动检查；真机与现场定位尚未验收。**

## 代码架构

| 模块 | 责任 |
|---|---|
| `MainActivity.kt` / `web/` | 线上 WebView 首页、同源原生桥、返回与通知导航 |
| `AriApplication.kt` / `TourRuntime` | 景区数据、定位状态、前后台状态与页面 / 悬浮窗之间的协调 |
| `tour/` | 景区数据解析、数据仓库、与 Android 无关的到站判定 |
| `service/` | location 前台服务、GPS / 网络定位来源、到站通知 |
| `overlay/` | 拖动头像、气泡、到站消息、公开文字问答面板 |
| `network/` | 现有 `/api/tour/{馆}/places/{地点}/topics` 的读取与提交 |
| `data/` | 匿名设备号、陪伴与导览员设置、本机到站消息 |
| `ui/` | 配色与基础控件、导览员配置、陪伴与权限设置 |
| `app/src/debug/` | 只在 debug 包中的定位注入入口 |

位置流：`LocationSource → TourService → GeofenceEngine → TourRuntime → 页面 / 通知 / 悬浮窗`。
文字提问流：`网页或悬浮窗 → 同一个匿名设备号 → 已有公开问答 API`。
新增景区放入 `web_api/tour/data/*.json`；形象先替换 `ui/Guides`，正式素材后续接入。

## 迁移到 Mac

1. 迁移**整个仓库**；App不再打包网页和景区资料，单元测试仍使用 `web_api/tour/data/` 的真实资料夹具。
2. 不复制 Windows 的 `local.properties`、`build/`、`.gradle/`、临时缓存或本机签名文件，它们已被 Git 忽略。
3. 在 Android Studio 打开 `android/`，安装 SDK Platform 35 / Build-Tools 35.0.0，为本项目选择 JDK 17 或 21。
   Studio 自带运行时与项目构建 JDK 是两项设置；当前项目优先用 JDK 21，避免直接套用旧 Mac 草案的运行时版本。
4. 让 Studio 为本机生成 SDK 路径；或创建 `android/local.properties`，写 `sdk.dir=/Users/<用户名>/Library/Android/sdk`。
5. 后续在 Mac 构建时使用 `sh gradlew :app:assembleDebug`，或 Studio 的构建与运行按钮；运行验证由你在 Mac 上继续。

Gradle Wrapper、构建脚本和 Kotlin 源码均在工程内，不依赖本机 PyCharm 路径。`tools/` 的离线备用脚本属于当前机器的辅助工具，通常直接使用 Gradle 即可。

## 打开与构建

在 Android Studio 打开本目录；使用 SDK Platform 35、Build-Tools 35.0.0 和兼容的 JDK。
项目固定 Gradle 8.11.1 / AGP 8.9.2 / Kotlin 2.0.21 / minSdk 26 / targetSdk 35。
Gradle Wrapper 的 JAR 从本机 Gradle 8.11.1 官方分发包内提取；首次运行需要下载其分发包与 Maven 依赖。

Windows 示例（当前机器可用的 JBR 21 在 PyCharm 安装目录里）：

```powershell
python android/tools/build.py --java-home 'D:\Program Files\JetBrains\PyCharm Community Edition 2024.3\jbr' --sdk 'C:\Users\cangj\AppData\Local\Android\Sdk'
```

已有 `JAVA_HOME`、`ANDROID_HOME` 或 `local.properties` 时：

```powershell
cd android
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

macOS / Linux 用 `sh gradlew`。APK 产物为 `app/build/outputs/apk/debug/app-debug.apk`。
`local.properties`、Gradle 缓存与 APK 不进 Git；签名密钥不进 Git。

## APK 下载

下载地址：[https://tour.snowmeet.top/android/app](https://tour.snowmeet.top/android/app)。
2026-10-15早先发布的旧包内置伪满皇宫资料；本轮改为直接打开线上Web首页，必须安装新包一次。
此后景区增减、排序和内容更新只发布服务器资料，无需重发App。当前构建与签名记录见 `utils/import_data/wanping_android_report.json`；真机未验收。
服务器存放位置、SHA-256 和更新方法见 `docs/TOUR_WEB.md` 的「Android APK 下载」。

## 数据与网页

WebView直接打开 `https://tour.snowmeet.top/index.html`。`catalog.json` 决定已发布景区及顺序，`data/<key>.json` 提供同一份地图、路线、介绍。
网页把成功取得的完整资料同步给原生定位、通知与悬浮导览；增删与排序一起替换，错误资料不覆盖最后有效缓存。回到前台和返回首页时刷新。
首次打开需要联网；本机缓存只用于最后一次有效的定位资料，不能当作实时开放保证，不承诺完整离线网页。
Android不再把网页、景区清单或资料复制进APK，不写死景区key；当前服务器资料包括伪满皇宫和宛平城。
宛平城含39条资料、7个有位置依据的到达点，以及免费线和全面线，费用及开放边界见页面路线提示和 `docs/WANPING_DATA.md`。
修改服务器 `catalog.json` 的数组可调整顺序、上架或下架；新增资料首次生成时会追加到清单。无需重新构建APK；不上传轨迹。

首次启动说明按实际行为写明：定位在本机判定；文字问题与匿名设备号发给现有服务；问答可能公开。
**本地测试不要对线上提交测试问题**：会入库并可能向游客公开。自动测试使用假的问答接口，不调用模型或生产数据库。

## 陪伴功能

1. 进入地图后申请精确定位。近景区每 3 秒请求 GPS，离全部景区 1 公里以上时降到 60 秒；网络定位只显示参考位置，不触发到站。
2. 在“陪伴设置”开启后台定位与到站提醒、悬浮导览员，并允许通知和悬浮窗。
3. App 在前台时用页面到站横幅；退到后台后用系统通知与悬浮气泡。回前台从本机持久消息记录补齐参观进度。
4. 头像支持拖动贴边，闲置时变淡；点击展开最近到站消息、景区 / 景点选择、公开文字问答、打开地图与停止陪伴。
5. 锁屏时隐藏悬浮窗。前台服务始终从可见的 App 启动；进程被系统停止或重启后需要重新打开 App，不在后台自动重启。
6. 小米 / 红米的自启动、省电策略、悬浮窗权限需在真机设置中开启；应用详情页提供入口和说明。

后台继续定位使用 location 前台服务，不申请录音、开机唤醒或麦克风服务。
页面原来的浏览器定位在 `AriHost` 模式下停用，状态由原生 `GeofenceEngine` 推送；普通网页模式沿用原逻辑。

## 验证

```powershell
$env:CHROME='C:\Program Files\Google\Chrome\Application\chrome.exe'
node web_api/tests/tour_browser_check.mjs
python android/tools/build.py --java-home '<JDK目录>' --sdk '<SDK目录>'
```

浏览器 `fixture` 场景通过真实 `watchPosition` 生成 `testdata/geofence_cases.json`；Kotlin 单测逐项回放，比较状态、热区与画布坐标。
受限环境无法运行浏览器时，`node android/tools/geofence_fixture.mjs` 从实际 `app.js` 函数离线生成夹具，文件中明确标出来源；这不验证浏览器的定位回调。
几何单测还覆盖重叠热区、1.2 倍离开半径、30 米精度闸、网络位置不触发、信号中断和范围外复位。
`host` 场景验证原生状态、消息幂等、通知打开介绍、返回键与不启动浏览器 GPS。

Debug 包可注入定位（仅已启动的服务接受；release 不包含此 receiver）：

```powershell
adb shell am broadcast -a top.snowmeet.tour.DEBUG_FIX -n top.snowmeet.tour/.debug.FixReceiver --es lat 43.90398 --es lon 125.34323 --es acc 5
```

真机需要核对 GPS 精度、后台省电策略、锁屏通知、悬浮面板软键盘和拒绝 / 撤销权限后的表现。
构建与自动检查不能代替这些现场验收。

## 已有检查记录与未完成项（2026-10-14）

- 较早的源码版本通过 SDK 直接构建 Debug APK：Kotlin 编译、AAPT2、D8、zipalign、APK v2 / v3 签名验证完成。
  用户随后明确只要代码架构、迁移到 Mac 再测试，因此最后一轮打包已中断；本机 APK 是临时产物，不代表最新源码或验收通过。
- 离线 Kotlin / JUnit：9 项通过，包含真实数据解析与 182 条从 `app.js` 实际函数生成的状态序列对照。
- 此前的 JavaScript 语法、XML、Python 辅助工具与补丁格式检查通过；停止测试后没有继续补验最新改动。
- Gradle / AGP 标准构建与 lint 尚未跑完：受限环境无法连接本机 Gradle daemon，自动权限审查两次超时。
- Chrome 运行验收、模拟器安装和小米 / 红米真机验收尚未完成；本次没有连接生产数据库、提交线上测试问答或部署服务器。

SDK 备用构建命令（需已有 API 35 SDK、Build-Tools 35.0.0 和 Kotlin 2.0.21 缓存）：

```powershell
python android/tools/build_with_sdk.py --java-home '<JDK目录>' --sdk '<SDK目录>'
```

此备用命令不运行 AGP 或 lint；通常开发与后续 CI 仍使用 Gradle Wrapper。

版本依据：[AGP 8.9 兼容矩阵](https://developer.android.com/build/releases/agp-8-9-0-release-notes)、
[HTTPS 下加载本地 WebView 内容](https://developer.android.com/develop/ui/views/layout/webapps/load-local-content)、
[location 前台服务](https://developer.android.com/develop/background-work/services/fgs/service-types#location)。
