package top.snowmeet.tour.tour

import org.json.JSONArray
import org.json.JSONObject

data class Point(val x: Double, val y: Double)
data class Projection(val lat0: Double, val lon0: Double, val mlat: Double, val mlon: Double,
    val a: Double, val b: Double, val c: Double, val d: Double, val tx: Double, val ty: Double) {
    fun project(lat: Double, lon: Double): Point {
        val east = (lon - lon0) * mlon
        val north = (lat - lat0) * mlat
        return Point(a * east + b * north + tx, c * east + d * north + ty)
    }
}
data class Place(val id: String, val name: String, val center: Point, val radius: Double, val introduction: String)
data class TourData(val key: String, val name: String, val projection: Projection, val pixelsPerMeter: Double,
    val area: List<Point>, val buffer: Double, val entrance: Point, val entranceLat: Double,
    val entranceLon: Double, val places: List<Place>) {
    companion object {
        fun parse(text: String): TourData {
            val root = JSONObject(text)
            val p = root.getJSONObject("proj")
            val entrance = root.getJSONObject("entrance")
            val area = root.getJSONObject("area")
            val stops = root.getJSONObject("stops")
            val places = root.getJSONArray("places").objects().map { place ->
                val intro = place.optJSONArray("stops")?.let { seqs ->
                    (0 until seqs.length()).mapNotNull { i -> stops.optJSONObject(seqs.get(i).toString()) }
                        .joinToString("\n\n") { stop -> stop.optJSONArray("intro")?.let { paragraphs ->
                            (0 until paragraphs.length()).joinToString("\n") { paragraphs.getString(it) }
                        }.orEmpty() }
                }.orEmpty()
                Place(place.getString("id"), place.getJSONObject("name").getString("zh"),
                    Point(place.getDouble("x"), place.getDouble("y")), place.getDouble("r"), intro)
            }
            require(places.map { it.id }.distinct().size == places.size) { "Duplicate place id" }
            require(places.all { it.radius > 0 }) { "Invalid hot-zone radius" }
            return TourData(root.getString("key"), root.getJSONObject("card").getJSONObject("short").getString("zh"),
                Projection(p.getDouble("lat0"), p.getDouble("lon0"), p.getDouble("mlat"), p.getDouble("mlon"),
                    p.getDouble("a"), p.getDouble("b"), p.getDouble("c"), p.getDouble("d"), p.getDouble("tx"), p.getDouble("ty")),
                root.getJSONObject("canvas").getDouble("px_per_m"),
                area.getJSONArray("poly").let { points -> (0 until points.length()).map { i ->
                    points.getJSONArray(i).let { Point(it.getDouble(0), it.getDouble(1)) }
                } }, area.getDouble("buffer"), Point(entrance.getDouble("x"), entrance.getDouble("y")),
                entrance.getDouble("lat"), entrance.getDouble("lon"), places)
        }
    }
}
fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
