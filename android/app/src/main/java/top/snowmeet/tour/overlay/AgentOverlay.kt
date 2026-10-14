package top.snowmeet.tour.overlay

import android.app.KeyguardManager
import android.content.*
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputFilter
import android.view.*
import android.widget.*
import java.util.concurrent.Executors
import org.json.JSONObject
import top.snowmeet.tour.MainActivity
import top.snowmeet.tour.TourRuntime
import top.snowmeet.tour.network.TourApi
import top.snowmeet.tour.service.TourService
import top.snowmeet.tour.tour.TourData
import top.snowmeet.tour.ui.*

class AgentOverlay(private val context: Context) {
    private val manager = context.getSystemService(WindowManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private val api = TourApi(TourRuntime.preferences.visitor)
    private var avatar: TextView? = null
    private var bubble: TextView? = null
    private var panel: LinearLayout? = null
    private var status: TextView? = null
    private var topics: LinearLayout? = null
    private var arrivalMessages: LinearLayout? = null
    private var panelMuseum: TourData? = null
    private var panelPlace: String? = null
    private var lastArrival = 0L
    private var lastContext: Pair<String, String>? = null
    private var generation = 0
    private var asking = false
    private var lastError = false
    private var submit: Button? = null
    private var editor: EditText? = null
    private var draft = ""
    private val idle = Runnable { avatar?.alpha = 0.65f; hideBubble() }
    private val params = WindowManager.LayoutParams(dp(56), dp(56), WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL, PixelFormat.TRANSLUCENT).apply {
        gravity = Gravity.TOP or Gravity.LEFT
    }
    private fun dp(value: Int) = Ui.dp(context, value)
    private fun width() = context.resources.displayMetrics.widthPixels
    private fun height() = context.resources.displayMetrics.heightPixels
    private fun shouldShow() = TourRuntime.preferences.companion && TourRuntime.preferences.overlay && !TourRuntime.foreground &&
        Settings.canDrawOverlays(context) && !context.getSystemService(KeyguardManager::class.java).isKeyguardLocked &&
        context.getSystemService(android.os.PowerManager::class.java).isInteractive

    fun refresh() {
        if (!shouldShow()) { hide(); return }
        if (avatar == null) createAvatar()
        val guide = Guides.find(TourRuntime.preferences.guide)
        avatar?.text = guide.glyph
        avatar?.background = Ui.card(context, guide.color, 28)
        val latest = TourRuntime.arrivals.all().firstOrNull()
        if (latest != null && latest.time > lastArrival) {
            lastArrival = latest.time
            showBubble("已到达：${latest.name}")
        }
        if (!asking && !lastError) status?.text = contextLabel()
        renderArrivals()
    }
    fun resetLayout() { hide(); refresh() }
    private fun createAvatar() {
        params.x = if (TourRuntime.preferences.overlayRight) width() - dp(64) else dp(8)
        params.y = TourRuntime.preferences.overlayY.coerceIn(dp(32), (height() - dp(110)).coerceAtLeast(dp(32)))
        val view = TextView(context).apply {
            textSize = 23f; gravity = Gravity.CENTER; setTextColor(Color.WHITE)
            contentDescription = "悬浮导览员，点击打开文字互动，拖动调整位置"
            elevation = dp(8).toFloat()
        }
        var startX = 0; var startY = 0; var rawX = 0f; var rawY = 0f; var moved = false
        view.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> { startX = params.x; startY = params.y; rawX = event.rawX; rawY = event.rawY; moved = false; view.alpha = 1f; handler.removeCallbacks(idle) }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - rawX; val dy = event.rawY - rawY
                    if (kotlin.math.hypot(dx, dy) > dp(6)) moved = true
                    if (moved) {
                        hideBubble()
                        params.x = (startX + dx.toInt()).coerceIn(0, width() - dp(56))
                        params.y = (startY + dy.toInt()).coerceIn(dp(24), height() - dp(90))
                        runCatching { manager.updateViewLayout(view, params) }
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) openPanel()
                    else {
                        TourRuntime.preferences.overlayRight = params.x + dp(28) > width() / 2
                        params.x = if (TourRuntime.preferences.overlayRight) width() - dp(64) else dp(8)
                        TourRuntime.preferences.overlayY = params.y
                        runCatching { manager.updateViewLayout(view, params) }
                    }
                    handler.postDelayed(idle, 8000)
                }
            }
            true
        }
        runCatching { manager.addView(view, params); avatar = view; handler.postDelayed(idle, 8000) }
    }
    private fun contextLabel(): String {
        val museum = panelMuseum ?: TourRuntime.repository.find(TourRuntime.preferences.museum) ?: TourRuntime.repository.tours.first()
        val state = TourRuntime.state(museum.key)
        val name = museum.places.firstOrNull { it.id == state?.inside }?.name
        return if (name != null) "${museum.name} · 位于$name" else "${museum.name} · 未进入热区，可选择景点提问"
    }
    private fun showBubble(text: String) {
        hideBubble()
        if (panel != null) return
        val view = Ui.text(context, text, 14f).apply {
            background = Ui.card(context); setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { openPanel() }
        }
        val lp = WindowManager.LayoutParams(dp(220).coerceAtMost(width() - dp(80)), -2,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT).apply {
            gravity = Gravity.TOP or Gravity.LEFT
            x = if (params.x > width() / 2) (params.x - dp(228)).coerceAtLeast(dp(8)) else params.x + dp(64)
            y = params.y
        }
        runCatching { manager.addView(view, lp); bubble = view }
        handler.postDelayed(idle, 8000)
    }
    private fun hideBubble() { bubble?.let { runCatching { manager.removeView(it) } }; bubble = null }
    private fun closePanel() {
        generation++; panel?.let { runCatching { manager.removeView(it) } }
        panel = null; topics = null; arrivalMessages = null; status = null; submit = null; editor = null
    }
    private fun openPanel() {
        closePanel(); hideBubble()
        val body = Ui.column(context).apply { background = Ui.card(context); setPadding(dp(14), dp(10), dp(14), dp(10)); elevation = dp(12).toFloat() }
        panel = body
        val head = LinearLayout(context)
        head.addView(Ui.text(context, "${Guides.find(TourRuntime.preferences.guide).name} · 文字互动", 18f, true), LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(Ui.button(context, "收起") { closePanel() })
        body.addView(head)
        status = Ui.text(context, contextLabel(), 13f)
        body.addView(status)
        val museumSpinner = Spinner(context)
        val placesSpinner = Spinner(context)
        body.addView(museumSpinner); body.addView(placesSpinner)
        val tours = TourRuntime.repository.tours
        museumSpinner.adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, tours.map { it.name })
        panelMuseum = TourRuntime.repository.find(TourRuntime.preferences.museum) ?: tours.first()
        museumSpinner.setSelection(tours.indexOf(panelMuseum))
        fun selectPlaces(tour: TourData) {
            panelMuseum = tour
            placesSpinner.adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, tour.places.map { it.name })
            val inside = TourRuntime.state(tour.key)?.inside
            val preferred = tour.places.indexOfFirst { it.id == (panelPlace ?: inside) }
            placesSpinner.setSelection(preferred.coerceAtLeast(0))
        }
        museumSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { panelPlace = null; selectPlaces(tours[position]); status?.text = contextLabel() }
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        placesSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val museum = panelMuseum ?: return
                panelPlace = museum.places[position].id
                loadTopics(museum.key, panelPlace!!)
            }
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        val scroll = ScrollView(context)
        val scrollBody = Ui.column(context)
        arrivalMessages = Ui.column(context)
        topics = Ui.column(context)
        scrollBody.addView(arrivalMessages)
        scrollBody.addView(topics)
        scroll.addView(scrollBody)
        renderArrivals()
        body.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        body.addView(Ui.text(context, "提交前请知悉：问题与回答可能向所有游客公开；AI 回答可能有误。", 12f).apply { setTextColor(Ui.accent) })
        val input = EditText(context).apply { hint = "输入关于所选景点的问题"; setText(draft); filters = arrayOf(InputFilter.LengthFilter(100)); maxLines = 3 }
        editor = input
        body.addView(input)
        val actions = LinearLayout(context)
        val send = Ui.button(context, "提交公开问答") {}
        submit = send
        send.isEnabled = !asking
        send.setOnClickListener {
            val museum = panelMuseum ?: return@setOnClickListener
            val place = panelPlace ?: return@setOnClickListener
            val question = input.text.toString().trim()
            if (question.length !in 2..100) { input.error = "请输入 2–100 字的问题"; return@setOnClickListener }
            if (asking) return@setOnClickListener
            draft = question; asking = true; lastError = false; send.isEnabled = false
            status?.text = "${Guides.find(TourRuntime.preferences.guide).name}正在思考…"
            val token = generation
            io.execute {
                val result = runCatching { api.ask(museum.key, place, question) }
                handler.post {
                    asking = false
                    submit?.isEnabled = true
                    if (result.isSuccess) {
                        draft = ""
                        if (editor?.text?.toString()?.trim() == question) editor?.setText("")
                    }
                    if (token != generation) { refresh(); return@post }
                    send.isEnabled = true
                    result.onSuccess { payload ->
                        draft = ""; input.setText(""); status?.text = "已提交 · 问答可能公开"
                        val topic = payload.getJSONObject("topic")
                        if (panelMuseum?.key == museum.key && panelPlace == place) addTopic(topic)
                        showBubble(topic.optString("answer").take(50))
                    }.onFailure { lastError = true; status?.text = "提交失败：${it.message ?: "请检查网络后重试"}" }
                }
            }
        }
        actions.addView(send, LinearLayout.LayoutParams(0, -2, 1f))
        actions.addView(Ui.button(context, "打开地图") { openMap() }, LinearLayout.LayoutParams(0, -2, 1f))
        body.addView(actions)
        body.addView(Ui.button(context, "停止陪伴") {
            TourRuntime.preferences.companion = false
            context.startService(Intent(context, TourService::class.java).setAction(TourService.ACTION_STOP))
            hide()
        })
        selectPlaces(panelMuseum!!)
        val lp = WindowManager.LayoutParams((width() - dp(24)).coerceAtMost(dp(420)), (height() * 0.68).toInt(),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT).apply { gravity = Gravity.CENTER; softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE }
        runCatching { manager.addView(body, lp) }.onFailure { panel = null; showBubble("无法打开面板，请返回 App 检查悬浮窗权限。") }
    }
    private fun loadTopics(museum: String, place: String) {
        lastError = false
        val contextKey = museum to place
        lastContext = contextKey
        topics?.removeAllViews()
        topics?.addView(Ui.text(context, "正在载入公开问答…", 13f))
        val token = generation
        io.execute {
            val result = runCatching { api.list(museum, place) }
            handler.post {
                if (token != generation || lastContext != contextKey) return@post
                topics?.removeAllViews()
                result.onSuccess { payload ->
                    val rows = payload.getJSONArray("topics")
                    if (rows.length() == 0) topics?.addView(Ui.text(context, "这里还没有问答。", 13f))
                    for (i in 0 until rows.length()) addTopic(rows.getJSONObject(i), append = true)
                }.onFailure { topics?.addView(Ui.text(context, "问答暂不可用：${it.message}\n可打开地图查看已下载的介绍。", 13f)) }
            }
        }
    }
    private fun renderArrivals() {
        val container = arrivalMessages ?: return
        container.removeAllViews()
        val records = TourRuntime.arrivals.all().take(3)
        if (records.isEmpty()) return
        container.addView(Ui.text(context, "最近到站", 13f, true))
        val format = java.text.SimpleDateFormat("HH:mm", java.util.Locale.CHINA)
        records.forEach { arrival ->
            container.addView(Ui.button(context, "${format.format(java.util.Date(arrival.time))} · ${arrival.name}") {
                context.startActivity(Intent(context, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra("museum", arrival.museum).putExtra("place", arrival.place))
                hide()
            })
        }
        container.addView(Ui.text(context, "所选景点的公开问答", 13f, true))
    }
    private fun addTopic(topic: JSONObject, append: Boolean = false) {
        val answer = if (topic.isNull("answer")) "暂未收到回答" else topic.getString("answer")
        val view = Ui.text(context, "${if (topic.optBoolean("mine")) "我的" else "游客"}提问：${topic.optString("question")}\n\n$answer\n\nAI 生成 · ${if (topic.optBoolean("public")) "公开" else "仅自己可见"}", 14f)
        view.setTextIsSelectable(true)
        topics?.addView(view, if (append) -1 else 0)
    }
    private fun openMap() {
        context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra("museum", panelMuseum?.key).putExtra("place", panelPlace))
        hide()
    }
    private fun hide() { closePanel(); hideBubble(); avatar?.let { runCatching { manager.removeView(it) } }; avatar = null; handler.removeCallbacks(idle) }
    fun destroy() { hide(); io.shutdownNow() }
}
