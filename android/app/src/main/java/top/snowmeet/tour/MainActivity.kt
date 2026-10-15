package top.snowmeet.tour

import android.Manifest
import android.annotation.SuppressLint
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.net.Uri
import android.os.*
import android.view.*
import android.webkit.*
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import top.snowmeet.tour.service.TourService
import top.snowmeet.tour.ui.*
import top.snowmeet.tour.web.HostBridge

class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var frame: FrameLayout
    private lateinit var guideButton: Button
    private var selected: String? = null
    private var pageReady = false
    private var connectedAt = System.currentTimeMillis()
    private var pendingPlace: String? = null
    private var requestCompanion = false
    private var refreshOnResume = false
    private val changed: () -> Unit = { if (::web.isInitialized) { updateGuide(); pushState() } }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // API 26只有浅色导航按钮；27起才可在浅色导航栏上使用深色按钮。
        if (Build.VERSION.SDK_INT >= 27) {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = window.decorView.systemUiVisibility or android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
            @Suppress("DEPRECATION")
            window.navigationBarColor = Ui.background
        }
        val layout = Ui.column(this).apply { setBackgroundColor(Ui.background) }
        layout.setOnApplyWindowInsetsListener { view, insets ->
            if (Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION") view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        val toolbar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(Ui.dp(this@MainActivity, 8), 0, Ui.dp(this@MainActivity, 8), 0) }
        guideButton = Ui.button(this, "阿瑞") { showSettings() }
        toolbar.addView(guideButton, LinearLayout.LayoutParams(0, Ui.dp(this, 48), 1f))
        toolbar.addView(Ui.button(this, "陪伴设置") { showSettings() })
        layout.addView(toolbar)
        frame = FrameLayout(this)
        layout.addView(frame, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(layout)
        web = WebView(this)
        frame.addView(web, FrameLayout.LayoutParams(-1, -1))
        web.settings.apply {
            javaScriptEnabled = true; domStorageEnabled = true
            allowFileAccess = false; allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        web.addJavascriptInterface(HostBridge(this), "AriHost")
        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                pageReady = false
            }
            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest): WebResourceResponse? {
                if (!isOwnOrigin(request.url))
                    return WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", emptyMap(), "Blocked".byteInputStream())
                return null // Own-origin pages, scripts, data and API all come from the server.
            }
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest): Boolean {
                if (isOwnOrigin(request.url) && request.url.path in setOf("/", "/index.html")) return false
                if (request.isForMainFrame && request.url.scheme in setOf("https", "http")) runCatching { startActivity(Intent(Intent.ACTION_VIEW, request.url)) }
                return true
            }
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) showRetry()
            }
        }
        updateGuide()
        handleIntent(intent)
        loadPage()
        if (!TourRuntime.preferences.onboarding) AlertDialog.Builder(this)
            .setTitle("欢迎使用 Ari Travel")
            .setMessage("首页、地图和景点资料从导览网站更新，首次打开需要联网；景区增减与排序随网站同步。允许精确定位后可提醒到站；开启陪伴模式后会继续在后台使用定位。\n\n文字提问发送到导览站，问题与回答可能向所有游客公开。当前版本没有语音和轨迹上传功能。")
            .setPositiveButton("开始导览") { _, _ -> TourRuntime.preferences.onboarding = true }
            .setCancelable(false).show()
    }
    private fun loadPage() {
        pageReady = false
        val key = intent.getStringExtra("museum") ?: TourRuntime.preferences.museum
        intent.removeExtra("museum"); intent.removeExtra("place")
        val hash = TourRuntime.repository.find(key)?.key?.let { "#$it" }.orEmpty()
        web.loadUrl("${BuildConfig.TOUR_ORIGIN}/index.html$hash")
    }
    private fun isOwnOrigin(uri: Uri) = uri.scheme == "https" && uri.host == Uri.parse(BuildConfig.TOUR_ORIGIN).host && (uri.port == -1 || uri.port == 443)
    private fun showRetry() {
        val panel = Ui.column(this).apply { gravity = Gravity.CENTER; setBackgroundColor(Ui.background) }
        panel.addView(Ui.text(this, "导览页面没有载入成功。", 18f))
        panel.addView(Ui.button(this, "重试") { frame.removeView(panel); loadPage() })
        frame.addView(panel, FrameLayout.LayoutParams(-1, -1))
    }
    override fun onStart() {
        super.onStart(); TourRuntime.setForeground(true); TourRuntime.listeners.add(changed)
    }
    override fun onResume() {
        super.onResume(); connectedAt = System.currentTimeMillis(); updateGuide()
        if (refreshOnResume) { refreshOnResume = false; web.reload() }
        if (selected != null) {
            if (hasLocation()) startTracking() else TourRuntime.error("denied")
        }
        pushState()
    }
    override fun onStop() {
        refreshOnResume = true
        TourRuntime.listeners.remove(changed); TourRuntime.setForeground(false)
        if (!TourRuntime.preferences.companion) stopService(Intent(this, TourService::class.java))
        super.onStop()
    }
    override fun onDestroy() { web.removeJavascriptInterface("AriHost"); web.destroy(); super.onDestroy() }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent); setIntent(intent); handleIntent(intent)
        if (!pageReady) loadPage()
    }
    private fun handleIntent(intent: Intent) {
        val museum = intent.getStringExtra("museum") ?: return
        if (TourRuntime.repository.find(museum) == null) return
        pendingPlace = intent.getStringExtra("place")
        if (::web.isInitialized && pageReady) {
            web.evaluateJavascript("location.hash=${JSONObject.quote(museum)}", null)
            if (selected == museum) pushState()
            intent.removeExtra("museum"); intent.removeExtra("place")
        }
    }
    fun selectMuseum(key: String?) {
        if (key != null && TourRuntime.repository.find(key) == null) return
        selected = key; TourRuntime.preferences.museum = key; pageReady = key != null
        connectedAt = System.currentTimeMillis()
        if (key != null) { if (hasLocation()) startTracking() else requestLocation(); pushState() }
    }
    fun onCatalogChanged() {
        val removed = selected != null && TourRuntime.repository.find(selected) == null
        if (removed) {
            selected = null; pendingPlace = null; pageReady = false
            TourRuntime.preferences.museum = null
        }
        if (removed || TourRuntime.repository.tours.isEmpty()) setCompanion(false)
        pushState()
    }
    private fun updateGuide() {
        val guide = Guides.find(TourRuntime.preferences.guide)
        guideButton.text = "${guide.name} · ${if (TourRuntime.preferences.companion) "陪伴中" else "导览员"}"
    }
    private fun pushState() {
        val key = selected ?: return
        if (!pageReady || !TourRuntime.foreground) return
        val state = TourRuntime.snapshot(key).put("history", JSONArray(TourRuntime.arrivals.all(key).map { it.json() }))
            .put("connectedAt", connectedAt)
        web.evaluateJavascript("window.AriTour && AriTour.state($state)", null)
        pendingPlace?.let { place ->
            web.evaluateJavascript("window.AriTour && AriTour.open(${JSONObject.quote(place)})", null)
            pendingPlace = null
        }
    }
    fun showSettings() { CompanionSettings(this).show() }
    fun setCompanion(enabled: Boolean) {
        if (!enabled) {
            requestCompanion = false; TourRuntime.preferences.companion = false
            stopService(Intent(this, TourService::class.java))
            if (hasLocation() && selected != null) startTracking()
        } else if (!hasLocation()) { requestCompanion = true; requestLocation() }
        else { TourRuntime.preferences.companion = true; startTracking(); requestNotifications() }
        TourRuntime.notifyChanged()
    }
    fun requestLocation() {
        if (hasLocation()) { startTracking(); requestNotifications(); return }
        requestPermissions(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION), 101)
    }
    private fun requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 102)
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 101) {
            if (hasLocation()) {
                if (requestCompanion) TourRuntime.preferences.companion = true
                requestCompanion = false; startTracking(); requestNotifications()
            } else {
                requestCompanion = false; TourRuntime.preferences.companion = false; TourRuntime.error("denied")
                Toast.makeText(this, "到站提醒需要精确定位，可在应用权限中开启。", Toast.LENGTH_LONG).show()
            }
        }
        TourRuntime.notifyChanged()
    }
    private fun hasLocation() = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
    private fun startTracking() {
        if (!hasLocation()) return
        runCatching { startForegroundService(Intent(this, TourService::class.java)) }.onFailure {
            TourRuntime.error("unavailable"); Toast.makeText(this, "定位服务没有启动，请回到 App 重试。", Toast.LENGTH_LONG).show()
        }
    }
    @Deprecated("Deprecated in Android")
    override fun onBackPressed() {
        web.evaluateJavascript("window.AriTour ? AriTour.back() : false") { handled ->
            if (handled != "true") finish()
        }
    }
}
