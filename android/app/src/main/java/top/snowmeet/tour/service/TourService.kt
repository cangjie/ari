package top.snowmeet.tour.service

import android.Manifest
import android.app.Service
import android.content.*
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.*
import top.snowmeet.tour.TourRuntime
import top.snowmeet.tour.overlay.AgentOverlay
import top.snowmeet.tour.tour.*

class TourService : Service() {
    private lateinit var locations: LocationSource
    private lateinit var notifier: ArrivalNotifier
    private lateinit var overlay: AgentOverlay
    private val refresh: () -> Unit = {
        if (!TourRuntime.foreground && !TourRuntime.preferences.companion) stopSelf()
        else overlay.refresh()
    }
    private val screenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) { overlay.refresh() }
    }
    override fun onCreate() {
        super.onCreate()
        instance = this
        notifier = ArrivalNotifier(this)
        overlay = AgentOverlay(this)
        locations = LocationSource(this, ::onFix) {
            TourRuntime.error(it)
            if (it == "denied") { TourRuntime.preferences.companion = false; stopSelf() }
        }
        TourRuntime.listeners.add(refresh)
        val filter = IntentFilter().apply { addAction(Intent.ACTION_SCREEN_OFF); addAction(Intent.ACTION_SCREEN_ON); addAction(Intent.ACTION_USER_PRESENT) }
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(screenReceiver, filter, RECEIVER_NOT_EXPORTED)
        else registerReceiver(screenReceiver, filter)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            TourRuntime.preferences.companion = false
            stopSelf()
            TourRuntime.notifyChanged()
            return START_NOT_STICKY
        }
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            TourRuntime.preferences.companion = false
            TourRuntime.error("denied"); stopSelf(); return START_NOT_STICKY
        }
        if (Build.VERSION.SDK_INT >= 29) startForeground(ONGOING_ID, notifier.companion(), ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        else startForeground(ONGOING_ID, notifier.companion())
        if (!tracking) { tracking = true; locations.start() }
        overlay.refresh()
        return START_NOT_STICKY // Never silently restart a location FGS from the background.
    }
    private var tracking = false
    fun onFix(fix: Fix) {
        val arrivals = TourRuntime.onFix(fix)
        if (!TourRuntime.foreground && TourRuntime.preferences.companion) arrivals.forEach(notifier::arrival)
        val far = TourRuntime.repository.tours.all {
            GeofenceEngine.haversine(fix.latitude, fix.longitude, it.entranceLat, it.entranceLon) > 1000
        }
        locations.setFarAway(far)
    }
    override fun onBind(intent: Intent?) = null
    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig); overlay.resetLayout()
    }
    override fun onDestroy() {
        locations.stop(); overlay.destroy(); unregisterReceiver(screenReceiver)
        TourRuntime.listeners.remove(refresh)
        instance = null
        TourRuntime.error(if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) "unavailable" else "denied")
        super.onDestroy()
    }
    companion object {
        const val ACTION_STOP = "top.snowmeet.tour.STOP"
        const val ONGOING_ID = 100
        var instance: TourService? = null
            private set
    }
}
