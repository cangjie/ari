package top.snowmeet.tour.web

import android.webkit.JavascriptInterface
import org.json.JSONArray
import top.snowmeet.tour.MainActivity
import top.snowmeet.tour.TourRuntime

/** Exposed only to our HTTPS website; its catalog is authoritative for native geofences. */
class HostBridge(private val activity: MainActivity) {
    @JavascriptInterface fun museums(): String = JSONArray(TourRuntime.repository.tours.map { it.key }).toString()
    @JavascriptInterface fun catalog(text: String): Boolean = runCatching {
        TourRuntime.installCatalog(text)
        activity.runOnUiThread { activity.onCatalogChanged() }
        true
    }.getOrDefault(false)
    @JavascriptInterface fun visitorId(): String = TourRuntime.preferences.visitor
    @JavascriptInterface fun ready(museum: String) { activity.runOnUiThread { activity.selectMuseum(museum) } }
    @JavascriptInterface fun leave() { activity.runOnUiThread { activity.selectMuseum(null) } }
    @JavascriptInterface fun requestLocation() { activity.runOnUiThread { activity.requestLocation() } }
    @JavascriptInterface fun settings() { activity.runOnUiThread { activity.showSettings() } }
}
