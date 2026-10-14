package top.snowmeet.tour.data

import android.content.Context
import java.util.UUID

class AppPreferences(context: Context) {
    private val store = context.getSharedPreferences("ari", Context.MODE_PRIVATE)
    var companion: Boolean
        get() = store.getBoolean("companion", false)
        set(value) { store.edit().putBoolean("companion", value).apply() }
    var overlay: Boolean
        get() = store.getBoolean("overlay", false)
        set(value) { store.edit().putBoolean("overlay", value).apply() }
    var guide: String
        get() = store.getString("guide", "ari")!!
        set(value) { store.edit().putString("guide", value).apply() }
    var museum: String?
        get() = store.getString("museum", null)
        set(value) { store.edit().putString("museum", value).apply() }
    var onboarding: Boolean
        get() = store.getBoolean("onboarding", false)
        set(value) { store.edit().putBoolean("onboarding", value).apply() }
    var overlayY: Int
        get() = store.getInt("overlayY", 280)
        set(value) { store.edit().putInt("overlayY", value).apply() }
    var overlayRight: Boolean
        get() = store.getBoolean("overlayRight", true)
        set(value) { store.edit().putBoolean("overlayRight", value).apply() }
    val visitor: String = store.getString("visitor", null) ?: UUID.randomUUID().toString().also { store.edit().putString("visitor", it).apply() }
}
