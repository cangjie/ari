# Ari Travel Android App —— 实施计划（草案）

> **状态（2026-10-14 归档）：本次完成功能取舍记录与开发环境检查。Android 工程尚未创建，尚未构建或部署。**
> 用户先要求列清单、不忙实现，随后询问开发所需环境；本轮其余功能范围仍待确认。
> 当前取舍见下一节；下文保留的 2026-10-12 草案不能直接作为开工依据。

## 当前功能取舍（用户 2026-10-13）

编号沿用本次提供给用户的 25 项功能清单。

| 功能 | 决定 |
|---|---|
| 17：语音唤醒 | **取消** |
| 7：按住说话提问；16：悬浮头像语音提问 | **暂缓，未来可能需要**；本轮不实现 |

由上述取舍，本轮也不安排语音识别、录音、麦克风权限、唤醒词设置、监听状态，以及依赖语音输入的
18「语音操作指令」和 25「测试音频上传」。这些是当前范围调整的连带结果；未来是否恢复语音提问需另行确认，不能据此恢复语音唤醒。

8「回答朗读」、9「景点介绍朗读」、12「到站语音播报」属于语音输出，仍在待选清单中，尚未逐项确认。
其他功能继续等待用户取舍，不因本节更新而视为已批准实施。

## 功能清单（编号保持不变，供继续取舍）

依据原计划与用户提供的两页效果图整理。原件是 [Ari_Android_Design.pdf](Ari_Android_Design.pdf)，按原始字节归档；
其语音输入与唤醒界面属于旧范围，不能反过来覆盖用户的新取舍。
「复用网页」说明能力来源；「待确认」说明本轮尚未逐项选定。

| 编号 | 功能 | 内容 | 当前范围 |
|---|---|---|---|
| 1 | 多景区选择 | 景区列表与切换 | 复用网页 |
| 2 | 导游地图 | 地点与热区、缩放、拖动、回到当前位置 | 复用网页 |
| 3 | 参观路线 | 选路线、站点顺序与时间、上一站 / 下一站 | 复用网页 |
| 4 | 景点介绍 | 图片、介绍、评级、停留时间、出处 | 复用网页 |
| 5 | 前台到站提醒 | 到站横幅、消息与参观进度 | 复用网页 |
| 6 | 公开文字问答 | 景点介绍下面的游客互动 | 复用网页 |
| 7 | 按住说话提问 | 实时转写、松手发送、上滑取消 | 暂缓，未来可能需要 |
| 8 | 回答朗读 | 手动播放与停止 | 待确认 |
| 9 | 景点介绍朗读 | 播放与停止介绍 | 待确认 |
| 10 | 后台定位 | App 退到后台后继续取得位置 | 待确认 |
| 11 | 后台到站通知 | 到站后发通知，可打开地图或听介绍 | 待确认；听介绍依赖 9 |
| 12 | 到站语音播报 | 自动播报到站信息 | 待确认 |
| 13 | 悬浮导览员头像 | 拖动、贴边、闲置收起 | 待确认 |
| 14 | 悬浮气泡 | 到站信息与回答摘要 | 待确认；本轮无实时转写 |
| 15 | 悬浮对话面板 | 到站消息、文字问答、打开地图 | 待确认 |
| 16 | 悬浮头像语音提问 | 长按头像说话 | 暂缓，未来可能需要 |
| 17 | 语音唤醒 | 说唤醒词启动监听 | 取消 |
| 18 | 语音操作指令 | 讲一讲、打开地图、停止等口令 | 本轮不安排，依赖语音输入 |
| 19 | 导览员切换 | 切换头像、名字与自称 | 多导览员方向已定，具体方案待确认 |
| 20 | 导览员状态显示 | 待机、思考、播报、未读、暂不可用 | 待确认；本轮无监听状态 |
| 21 | 陪伴模式设置 | 后台提醒、悬浮窗、播报开关与停止陪伴 | 待确认；移除唤醒开关 |
| 22 | 权限与后台设置引导 | 定位、通知、悬浮窗与小米后台设置 | 随最终功能确定；本轮无麦克风权限 |
| 23 | 首次启动说明 | 收集、上传、使用说明 | 随最终功能确定 |
| 24 | 测试轨迹上传 | 上传定位点与判定结果供排查 | 待确认 |
| 25 | 测试音频上传 | 上传环境录音供排查 | 本轮不安排，当前无录音功能 |

悬浮问答仅自己可见、保留最近 3 轮、各导览员声音、包名等仍是旧草案的默认提议，未被本轮确认。

## 本机开发环境（2026-10-14 收工核对）

以下只描述当前 Intel Mac。2026-10-13 回答环境问题时尚未发现 Android Studio 与默认 SDK；
收工时两者已存在，安装不是本次代理执行的。不能沿用旧草案对其他时间点环境的断言。

| 项目 | 实查结果 |
|---|---|
| 机器 | Intel i7-7700HQ / x86_64，macOS 13.7.8，16 GB 内存，剩余约 20 GB 磁盘 |
| Android Studio | `/Applications/Android Studio.app`，版本 `2026.2`，build `AI-262.9437.185.2621.16467767` |
| Studio 自带 Java | JBR `25.0.3`，已执行 `java -version` 核对 |
| SDK | `~/Library/Android/sdk`，Platform `android-37.0`、Build-Tools `36.0.0` |
| Platform-Tools | SDK 中 adb `37.0.1`；命令行原有 `/usr/local/bin/adb` 是 `29.0.6`，使用时应指向 SDK 的新版 |
| Command-Line Tools | 尚未安装，SDK 下没有 `cmdline-tools` |
| 模拟器 | Emulator 和 API 37.0 Google Play x86_64 镜像已安装；AVD `Medium_Phone_API_37.0` 已配置，尚未验证启动 |
| 系统 Java | JDK `23.0.2`、`22.0.2`、`12.0.1`；命令行默认是 `23.0.2` |
| 构建缓存 | 未发现 `~/.gradle` 下的 Gradle / AGP / Kotlin 原草案缓存 |
| 工程与验收 | `android/` 未创建，APK 构建与真机连接未验证 |

开发前在 **Tools → SDK Manager** 补 Command-Line Tools，并按最终项目版本补需要的 SDK Platform / Build-Tools。
构建 JDK 与 Gradle / AGP / Kotlin 的版本组合需要重新核对，不能把原草案中的 JDK 22 与缓存版本直接套到当前安装。
Gradle 用项目 Wrapper 管理；Studio 和命令行采用一致的构建 JDK。安装了 API 37.0 不代表已经选定 compileSdk / targetSdk。
先用小米 / 红米真机验证，手机开启 USB 调试并接受连接授权；Mac 无需额外 USB 驱动。

安装说明参考：[Android Studio](https://developer.android.com/studio/install)、[SDK Manager](https://developer.android.com/studio/intro/update#sdk-manager)、
[构建 JDK](https://developer.android.com/build/jdks)、[Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)、
[真机调试](https://developer.android.com/studio/run/device)。

## 2026-10-12 原草案（历史参考）

> 原草案的「已定」记录当时的决定；「默认取舍」是 AI 提议，用户未逐项确认。
> 以下语音输入、唤醒、权限、测试和分期内容已由上面的当前取舍覆盖；待功能范围确认后再整体修订。
> 原效果图提示词在 `docs/TOUR_ANDROID_DESIGN_PROMPT.md`，其语音输入与唤醒界面也需按当前取舍调整。

## Context

导览站 <https://tour.snowmeet.top/> 现在是纯网页：定位靠浏览器的 `watchPosition`，页面一退到后台就不再到站提醒；
问答只有文字。用户要一个 Android App，在网页版基础上加四样网页做不到的东西：

1. 问答支持语音（照 MingnaCurator：按住说话、边说边出字、回答可朗读）
2. App 在后台时屏幕上留一个悬浮窗 agent，随时文字或语音互动
3. 后台持续定位，进入热区自动弹提示，agent 用语音和文字提醒
4. 语音唤醒

## 已定（用户 2026-10-12）

| 事项 | 决定 |
|---|---|
| 架构 | 原生 Kotlin 外壳 + WebView 复用 `web_api/tour`；四个新功能原生写 |
| 语音 | 讯飞实时听写 + AWS Polly 朗读。识别由服务器只签名、手机直连讯飞（服务器在美国，音频不绕太平洋） |
| 目录 | 仓库根目录 `android/`，由 Claude 创建 |
| 真机 | 小米 / 红米（HyperOS / MIUI） |

## 总体结构

```
android/  MainActivity ── WebView → https://tour.snowmeet.top/   （地图、路线、介绍、文字问答原样复用）
              │  AriHost / AriTour 桥
          TourService（前台服务：location + microphone）
              ├ LocationSource → GeofenceEngine ──→ 到站事件 ─┬→ 前台：交给页面横幅
              │   （app.js 到站逻辑的 Kotlin 移植）            └→ 后台：通知 + 悬浮窗 + 语音播报
              ├ AgentOverlay   悬浮头像 + 可展开的对话面板
              ├ WakeWord       sherpa-onnx 关键词检出（本机离线）
              └ VoiceSession   录音 → 讯飞（直连）→ 文字 → 问答接口 → Polly 朗读

web_api/  /api/tour/voice/asr-ticket        签一个讯飞连接地址（密钥不出服务器）
          /api/tour/…/speech                Polly 合成，按内容哈希缓存在服务器磁盘
          /api/tour/{馆}/agent/ask          悬浮窗与唤醒用的提问入口
```

**不为伪满皇宫写死任何东西**（用户 2026-10-12 定：它只是景点之一，日后至少加北海、香山、颐和园）。
景区清单来自 `web_api/tour/data/*.json`，后台服务同时盯着所有景区，文案里的景区名、地点名、评级都是数据；
某个景区缺路线、缺停留时间、缺照片时界面照常。App 里不出现 `wmhg` 这个字面量。

**一个运行环境里只有一个到站判定者**：网页版是 `app.js`，App 里是 `GeofenceEngine`（页面只负责画）。
两份实现靠同一份夹具对齐（见 M1），这是 AGENTS.md「两边各存一份必然分叉」那条教训的对策。

## 默认取舍（批准前可改，都是一处配置）

| 项 | 默认 | 说明 |
|---|---|---|
| agent 形象 | **不止一个，是一组可以换的导览员**（用户 2026-10-12 定）：先做阿瑞、小爱，以后还加。换人只换头像、名字和自称，界面与状态表达共用一套 | 效果图由用户用 Claude Design 出，提示词在 `docs/TOUR_ANDROID_DESIGN_PROMPT.md`；图回来之前先用占位头像 |
| 唤醒词 | 阿瑞用「你好阿瑞」；**小爱的唤醒词未定** | 「小爱同学」是小米语音助手的名字和唤醒词，测试机正是小米，带「小爱」的唤醒词会让两个助手同时应答。关键词是一行文本，可以同时挂多个，换词不用重训模型 |
| 朗读的声音 | 所有导览员共用一个女声 | Polly 的普通话音色只有 `Zhiyu` 一个（女声）。要各有各的声音得改用讯飞合成 |
| 悬浮窗里的问答 | **只有提问者自己看得到**，带最近 3 轮上下文 | 语音追问（「那他后来呢」）单独公开出来没有意义；介绍页里的问答照旧公开 |
| 位置与音频 | **前期都上传到服务器**（用户 2026-10-12 定，推翻了我原先写的「不出手机」；用户说明「目前就是个测试」）：全部定位点，以及开启语音唤醒期间麦克风收到的全部声音 | 按测试来做，取最简单的做法（以下是我定的）：全量上传、按设备与日期存成服务器磁盘上的文件、不设保存期限、手工清理；库里留一个开关，改一行就停。说明页与开关下的说明照实写「会上传」。对外发布前要重新过一遍，见「硬限制与风险」 |
| 到站语音 | 只播「已到达××」，介绍要点「听介绍」或说「讲一讲」才读 | 同一处 30 分钟内只语音播报一次，通知每次都发 |
| 包名 / 应用名 | `top.snowmeet.tour` / Ari Travel | |
| 系统版本 | minSdk 26（Android 8）、targetSdk 35 | 悬浮窗类型从 API 26 起才有 |
| 分发 | 直接装 APK | 上架应用商店（软著、备案）不在本计划内 |

## 分期（每一期结束都有可装的 APK 与验收记录，逐期提交）

### M0 工程骨架
- `android/`：Gradle 8.13 + AGP 8.9 + Kotlin 2.0.21（本机 `~/.gradle` 已有缓存），界面用 Views，不引入 Compose。
- `MainActivity`：WebView 只允许本站导航，外链交系统浏览器；返回键先交给页面；断网时显示原生重试页。
- `.gitignore` 增补：`android/.gradle/`、`android/**/build/`、`android/local.properties`、`*.jks`、`*.keystore`、拷贝进来的 assets、下载的 AAR 与模型。
- **先验工具链**：本机只有 JDK 22、没有 Android Studio，这套版本组合能不能出包要实跑才知道；不行就地调整并记下。
- 验：`./gradlew :app:assembleDebug` 出包；模拟器里看到列表页与地图（截图）。

### M1 后台定位与到站提醒（功能三的文字部分）
- `tour/GeofenceEngine.kt`：移植 [app.js](../web_api/tour/app.js) 的 `project / inPoly / distPoly / inArea / hitPlace / setPos`，
  连同 `ACC_TRIGGER_M = 30`、`STAY_FACTOR = 1.2`、当前热区 −0.2、「瞬时错误不清所在热区」。纯 Kotlin，无 Android 依赖。
- `tour/TourRepository.kt`：构建时由 Gradle 把 `web_api/tour/data/*.json` 拷进 assets（单一来源，不在仓库里存第二份）；联网时更新。
- `service/TourService.kt` + `LocationSource.kt`：`LocationManager.GPS_PROVIDER`。**只有卫星定位能触发到站**
  （原生 GPS 是 WGS-84，绕开了网页版的国测局坐标问题；网络定位只用来显示「距入口多远」）。离所有景区 1 公里以上降到 60 秒一次。
- `ArrivalNotifier.kt`：后台到站 → 高优先级通知（动作：听介绍 / 打开地图）；App 在前台时不发通知，交给页面横幅。
- 桥 `web/HostBridge.kt` + `app.js` 的 host 模式：检测到 `window.AriHost` 就不调 `navigator.geolocation`，
  改收原生推来的 `AriTour.state()` / `AriTour.arrive()`；回到前台时用 `AriTour.arrivals()` 补齐后台期间的到站消息。
  没有 `AriHost` 时网页版行为一字不变。
- debug 包留一个注入定位的入口（`adb shell am broadcast …`），与真实 GPS 走同一条 `onFix`，对应网页版的 `?fix=`。
- **测试期上传轨迹**：每个定位点（时间、经纬度、精度、来源、判定出的状态与所在热区）攒成一批，约 30 秒传一次到
  `POST /api/tour/debug/track`，服务端按设备与日期追加成 JSONL 文件，不进库。真机 GPS 至今没验过，这份轨迹正好拿来核对
  精度、到站时机和有没有国测局偏移。开关 `debug_upload` 放在 `tour_qa_setting`，设成 0 服务端拒收、App 随即停传。
- 验：
  - **夹具对齐**：`tour_browser_check.mjs` 新增一个场景，沿路线喂几百个定位，把页面给出的（状态、所在热区）序列存成
    `web_api/tests/fixtures/geofence_cases.json`；Kotlin 单测回放同一序列，必须逐项相同。以后改了 `app.js` 的到站逻辑，这一项会先红。
  - 浏览器验收原有 63 项照过，另加 host 模式场景（假的 `AriHost`）。
  - 模拟器：`adb emu geo fix` 沿路线回放，App 切后台、锁屏，`dumpsys notification` 里依次出现各站；回前台后「消息」列表齐全。

### M2 悬浮窗 agent，文字互动（功能二）
- `overlay/AgentOverlay.kt`、`AgentBubbleView.kt`、`AgentPanelView.kt`：`TYPE_APPLICATION_OVERLAY`，头像可拖动、贴边、记位置；
  点开是对话面板（到站消息、问答、输入框、「打开地图」「停止陪伴」）。**只在 App 不在前台时显示头像**；锁屏上不显示（系统限制），锁屏时靠通知与语音。
- 服务端 `POST /api/tour/{馆}/agent/ask`（[tour_qa.py](../web_api/app/tour_qa.py)）：复用现有的上限、存取与 `OpenAiAnswerer`；
  `build_system()` 一字不动（保住 OpenAI 的前缀缓存与介绍页问答的去重哈希），agent 的差异只放在 user 消息里
  （当前所在热区或「不在任何热区」、服务端自己查出的最近 3 轮、是否要朗读）。
  `tour_topic` 追加一列 `channel`（`page` / `agent`），介绍页列表只取 `page`。
- 「陪伴模式」设置面板（原生）：后台到站提醒 / 悬浮窗 / 语音播报 / 语音唤醒四个开关，各自显示权限状态与「去设置」。
  小米专项：悬浮窗、后台弹出界面、自启动、省电策略「无限制」、悬浮通知，跳转失败时退到应用详情页。
- 首次启动的隐私说明页（收集什么、何时上传、给谁）。
- 验：pytest 新增 agent 用例；模拟器里切后台后 `dumpsys window` 有悬浮窗，面板里提问得到回答，回前台头像消失。

### M3 语音（功能一、悬浮窗语音、到站播报）
- 服务端新模块 `web_api/app/tour_voice.py`：
  - `POST /api/tour/voice/asr-ticket`：照 `MingnaCurator/server_curator/Services/XfyunRealtimeAsrService.cs` 的 `BuildWebSocketUrl`
    签一个约 5 分钟有效的讯飞地址，连同 `app_id` 与识别参数返回。`APISecret` 不出服务器。
  - `GET /api/tour/topics/{id}/speech`、`GET /api/tour/{馆}/places/{地点}/speech?kind=arrive|intro`：
    **客户端只给编号，朗读的文字由服务端从库或导览 JSON 里取** —— 与页面显示的是同一份，也不会被当成免费的合成接口。
    Polly（`Zhiyu`）合成，按 `sha256(音色|引擎|文字)` 缓存在 `/var/cache/ari/tts/`。
  - 三道新上限放进 `tour_qa_setting`，现读、改库即生效、0 即关闭：`asr_per_visitor_per_day`、`asr_site_per_day`、`tts_chars_site_per_day`。
    问答与语音各读各的几行，缺语音那几行只让语音回 503，不连累已上线的文字问答。
  - 缺讯飞配置或缺 Polly 权限时对应接口回 503，App 里麦克风 / 朗读按钮不显示，其余照常（与现有问答同一套做法）。
- Android：`voice/Recorder.kt`（16 kHz 单声道）、`XfyunIatClient.kt`（OkHttp WebSocket，40 毫秒一帧，按 `wpgs` 的增补 / 替换拼出实时文字）、
  `VoiceSession.kt`、`SpeechPlayer.kt`（音频焦点、可打断）。
- 网页（仅 host 模式出现）：问答表单加「按住说话」（上滑取消，同 MingnaCurator），识别结果填进输入框后走原来的 `qaAsk`；每条回答加朗读按钮。
- 悬浮头像长按即说话；语音提的问题，回答自动朗读。
- 验：pytest（签名对照讯飞文档的算法独立算一遍、限流、缓存命中不再合成、503 降级）；
  在服务器上以服务身份各真调一次讯飞与 Polly；debug 包把一段 WAV 当麦克风输入，整链跑通并截图。

### M4 语音唤醒（功能四）
- `voice/WakeWord.kt`：sherpa-onnx 关键词检出，模型 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`（int8 编码器约 4.4 MB）。
  AAR 与模型由 `android/scripts/fetch_deps.sh` 下载并核对 sha256，不进仓库。**先看发布页的实际文件名再写脚本，不凭记忆猜。**
- 服务加 `microphone` 类型。唤醒 → 提示音 → 开始听（边连讯飞边本地缓冲，不丢开头）→ 提问 → 朗读。朗读期间暂停检出，免得自己唤醒自己。
- 整句等值匹配的几条口令：「讲一讲」读当前热区介绍、「打开地图」、「停」。其余一律当问题。
- 开机后发一条「点此恢复陪伴」的通知（系统不允许开机直接起麦克风服务，点通知才行）。
- **测试期上传音频**：唤醒监听开着时，麦克风的声音切成 10 秒一片传到 `POST /api/tour/debug/audio`，同时上传每次唤醒的时间与得分。
  存成文件，同上一个开关。优先用无损格式：录下来的真实环境音可以离线重放给唤醒模型，数漏唤醒与误唤醒，比放一段新闻准。
  Nginx 要给这个路径单独放宽请求体大小；部署前先看服务器磁盘还剩多少。
- 验：WAV 注入验整链；播 10 分钟无关语音数误唤醒次数；真机测一小时耗电。

### M5 小米真机验收与文档
- 真机逐项过：四项功能、杀后台后的恢复、各权限页跳转、软键盘是否挡输入框。
- `docs/TOUR_ANDROID.md`（构建、权限、上限怎么改、验收记录、已知限制）、`android/README.md`；
  `docs/TOUR_WEB.md` 与 `web_api/README.md` 补新接口；收工时 `AGENTS.md` 加子目录与一条新约定。

## 需要你提供 / 点头

| 什么 | 哪一期之前 | 说明 |
|---|---|---|
| 讯飞 AppID / APIKey / APISecret | M3 | 经标准输入写进服务器 `/etc/ari/`，不进仓库与命令行。控制台里 IP 白名单要关（手机直连），并确认服务量够用 |
| Polly 权限 | M3 | 给这台 EC2 挂一个带 `polly:SynthesizeSpeech` 的 IAM 角色（推荐，不用密钥），或给一对访问密钥 |
| 小米手机开 USB 调试 | 越早越好，最晚 M5 | 开发者选项里另要打开「USB 安装」 |
| 本机建一个模拟器 | M0 | 本机缺 `cmdline-tools`，要么你点头我下载，要么我手写 `~/.android/avd` 下的配置（仓库外的改动） |
| 每次服务器部署 | M2、M3 | 追加的 SQL、`pip install boto3`、新配置文件、重启 `ari-web-api`，动手前逐次确认 |
| agent 形象、唤醒词 | 随时 | 不给就用上面的默认 |

## 硬限制与风险（做不到的先说清）

- **唤醒不是字面上的「随时」**：只在陪伴模式开着时有效。期间通知栏常驻一条通知、状态栏麦克风绿点常亮、耗电明显增加（多少要真机测）。
  被系统杀掉或重启后要点一次通知或打开 App 才恢复。
- **小米会杀后台**：没给「自启动」「省电无限制」时，后台定位与唤醒随时可能停。引导页只能带用户去设置，替他开不了。
- **位置与音频的全量上传只适用于测试期**（工作项在 M1 与 M4）。流量与电量：16 kHz 单声道原始音频约 115 MB / 小时，无损压缩后大约减半。
  服务器在美国，国内游客的行踪轨迹与录音传过去属于个人信息出境，录下来的还有旁人的声音 —— 自己人测试无碍；
  **给游客用之前要把开关关掉，或者过告知、单独同意与保存期限这一关。**
- 别的应用占用麦克风时（微信语音、通话）唤醒会暂时失聪，结束后自动恢复。
- 室内 GPS 很差，到站提醒主要在走近建筑时触发 —— 与网页版相同，App 改变不了。
- 朗读只有中文音色；外语回答不显示朗读按钮。
- 讯飞与 Polly 的次数上限按内存计数，服务重启清零（与现有的每 IP 上限同一做法，避免再向你要一次 MySQL root 口令）。
- 网页从线上加载：首次打开要有网络；之后有缓存。
- 模拟器验不了的：国产系统杀后台、真实 GPS 精度、真实环境噪声下的唤醒率。这三样只在 M5 的真机上见分晓。

## 验证总表

```
cd web_api && ./.venv/bin/python -m pytest tests/ -q          # 原 64 条 + agent / 语音新增
node web_api/tests/tour_browser_check.mjs                     # 原 63 项 + host 模式 + 夹具生成与核对
cd android && ./gradlew :app:testDebugUnitTest                # 夹具回放、wpgs 拼接、口令匹配
cd android && ./gradlew :app:assembleDebug                    # 出包，装到模拟器 / 真机按各期的验收项走
```

## 不在本计划内

iOS、网页版的语音、应用商店上架、管理端、英文界面。

新景区的**数据接入**（路线、地图、`data/<馆>.json`）是数据管线的事，不在本计划内：北海公园库里已有 23 处景点的介绍与评级，
但没有路线数据；香山、颐和园还没有任何资料。App 这一侧不用为它们改代码，数据文件生成出来就能用。

## 依据

- 后台启动前台服务与麦克风 / 定位的限制：<https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start>
- Android 15 对前台服务类型与悬浮窗豁免的收紧：<https://developer.android.com/about/versions/15/changes/foreground-service-types>
- sherpa-onnx 关键词检出的预训练模型与自定义关键词：<https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html>
- Polly 可用音色（`Zhiyu`，标准与神经两种引擎）：<https://docs.aws.amazon.com/polly/latest/dg/available-voices.html>
