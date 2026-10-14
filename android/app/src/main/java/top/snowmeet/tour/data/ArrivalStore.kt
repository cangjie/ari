package top.snowmeet.tour.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import top.snowmeet.tour.tour.objects

data class Arrival(val museum: String, val place: String, val name: String, val time: Long) {
    fun json() = JSONObject().put("museum", museum).put("pid", place).put("name", name).put("at", time)
}
class ArrivalStore(context: Context) {
    private val prefs = context.getSharedPreferences("arrivals", Context.MODE_PRIVATE)
    private var items: MutableList<Arrival> = runCatching {
        JSONArray(prefs.getString("items", "[]")).objects().map {
            Arrival(it.getString("museum"), it.getString("pid"), it.getString("name"), it.getLong("at"))
        }.toMutableList()
    }.getOrDefault(mutableListOf())
    @Synchronized fun add(arrival: Arrival) {
        items.removeAll { it.museum == arrival.museum && it.place == arrival.place }
        items.add(0, arrival)
        items = items.take(200).toMutableList()
        prefs.edit().putString("items", JSONArray(items.map { it.json() }).toString()).apply()
    }
    @Synchronized fun all(museum: String? = null) = items.filter { museum == null || it.museum == museum }
}
