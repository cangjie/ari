package top.snowmeet.tour.service

import android.annotation.SuppressLint
import android.content.Context
import android.location.*
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import top.snowmeet.tour.tour.Fix

class LocationSource(context: Context, private val onFix: (Fix) -> Unit, private val onError: (String) -> Unit) {
    private val manager = context.getSystemService(LocationManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private var lastGps = 0L
    private var slow = false
    private val timeout = object : Runnable {
        override fun run() {
            if (System.currentTimeMillis() - lastGps > if (slow) 90_000 else 30_000) onError("timeout")
            handler.postDelayed(this, 15_000)
        }
    }
    private val listener = object : LocationListener {
        override fun onLocationChanged(location: Location) {
            if (!location.hasAccuracy() || System.currentTimeMillis() - location.time > 120_000) return
            if (location.provider == LocationManager.GPS_PROVIDER) lastGps = System.currentTimeMillis()
            else if (System.currentTimeMillis() - lastGps < 30_000) return
            onFix(Fix(location.latitude, location.longitude, location.accuracy.toDouble(), location.time, location.provider ?: "network"))
        }
        override fun onProviderDisabled(provider: String) { if (provider == LocationManager.GPS_PROVIDER) onError("unavailable") }
        override fun onProviderEnabled(provider: String) { onError("waiting") }
        @Deprecated("Deprecated in Android") override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
    }
    @SuppressLint("MissingPermission")
    fun start(farAway: Boolean = false) {
        stop()
        slow = farAway
        lastGps = System.currentTimeMillis()
        try {
            if (manager.allProviders.contains(LocationManager.GPS_PROVIDER))
                manager.requestLocationUpdates(LocationManager.GPS_PROVIDER, if (slow) 60_000L else 3_000L, 0f, listener, Looper.getMainLooper())
            if (manager.allProviders.contains(LocationManager.NETWORK_PROVIDER))
                manager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 30_000L, 0f, listener, Looper.getMainLooper())
            if (!manager.isProviderEnabled(LocationManager.GPS_PROVIDER)) onError("unavailable")
            handler.postDelayed(timeout, if (slow) 90_000 else 30_000)
        } catch (_: SecurityException) { onError("denied") }
    }
    fun setFarAway(value: Boolean) { if (slow != value) start(value) }
    fun stop() { manager.removeUpdates(listener); handler.removeCallbacks(timeout) }
}
