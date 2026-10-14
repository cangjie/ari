package top.snowmeet.tour.debug

import android.content.*
import android.util.Log
import top.snowmeet.tour.service.TourService
import top.snowmeet.tour.tour.Fix

/** Debug-only injection; cannot start the service or change release builds. */
class FixReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != "top.snowmeet.tour.DEBUG_FIX") return
        val service = TourService.instance ?: return
        runCatching {
            service.onFix(Fix(intent.getStringExtra("lat")!!.toDouble(), intent.getStringExtra("lon")!!.toDouble(),
                intent.getStringExtra("acc")?.toDouble() ?: 5.0, System.currentTimeMillis()))
        }.onFailure { Log.w("AriDebug", "Invalid injected fix", it) }
    }
}
