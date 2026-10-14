package top.snowmeet.tour

import android.app.Application
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import top.snowmeet.tour.data.*
import top.snowmeet.tour.tour.*

class AriApplication : Application() {
    override fun onCreate() { super.onCreate(); TourRuntime.initialize(this) }
}

object TourRuntime {
    lateinit var repository: TourRepository
    lateinit var preferences: AppPreferences
    lateinit var arrivals: ArrivalStore
    private val handler = Handler(Looper.getMainLooper())
    private var engines = emptyMap<String, GeofenceEngine>()
    val listeners = mutableSetOf<() -> Unit>()
    var foreground = false
        private set
    fun initialize(context: android.content.Context) {
        repository = TourRepository(context)
        preferences = AppPreferences(context)
        arrivals = ArrivalStore(context)
        engines = repository.tours.associate { it.key to GeofenceEngine(it) }
    }
    fun setForeground(value: Boolean) { foreground = value; notifyChanged() }
    fun state(key: String?) = engines[key]?.state
    fun error(status: String) { engines.values.forEach { it.error(status) }; notifyChanged() }
    fun onFix(fix: Fix): List<Arrival> {
        val entered = engines.mapNotNull { (key, engine) -> engine.onFix(fix).arrival?.let { Arrival(key, it.id, it.name, fix.time) } }
        entered.forEach(arrivals::add)
        notifyChanged()
        return entered
    }
    fun snapshot(key: String): JSONObject {
        val s = state(key) ?: return JSONObject()
        return JSONObject().put("museum", key).put("status", s.status).put("x", s.position.x).put("y", s.position.y)
            .put("acc", s.accuracy).put("dist", s.distance).put("inside", s.inside ?: JSONObject.NULL)
            .put("raw", s.fix?.let { JSONObject().put("lat", it.latitude).put("lon", it.longitude).put("acc", it.accuracy) } ?: JSONObject.NULL)
    }
    fun notifyChanged() { handler.post { listeners.toList().forEach { it() } } }
}
