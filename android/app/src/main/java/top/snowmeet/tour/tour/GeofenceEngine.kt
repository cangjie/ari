package top.snowmeet.tour.tour

import kotlin.math.*

data class Fix(val latitude: Double, val longitude: Double, val accuracy: Double, val time: Long,
    val provider: String = "gps") {
    init {
        require(latitude.isFinite() && latitude in -90.0..90.0)
        require(longitude.isFinite() && longitude in -180.0..180.0)
        require(accuracy.isFinite() && accuracy >= 0)
    }
}
data class TourState(val museum: String, val status: String, val position: Point, val accuracy: Double = 0.0,
    val distance: Double = 0.0, val inside: String? = null, val fix: Fix? = null)
data class Transition(val state: TourState, val arrival: Place?)

/** Pure Kotlin; mirrors app.js geometry, accuracy gate and 1.2x exit hysteresis. */
class GeofenceEngine(private val tour: TourData) {
    var state = TourState(tour.key, "waiting", tour.entrance)
        private set

    fun error(status: String): TourState {
        require(status in setOf("waiting", "denied", "timeout", "unavailable"))
        state = state.copy(status = status)
        return state // Temporary errors retain the current zone to avoid duplicate arrivals.
    }

    fun onFix(fix: Fix): Transition {
        val position = tour.projection.project(fix.latitude, fix.longitude)
        if (!inArea(position)) {
            state = TourState(tour.key, "outside", tour.entrance, fix.accuracy,
                haversine(fix.latitude, fix.longitude, tour.entranceLat, tour.entranceLon), null, fix)
            return Transition(state, null)
        }
        val trigger = fix.provider == "gps" && fix.accuracy <= ACCURACY_TRIGGER_METERS
        var inside = state.inside
        if (trigger) {
            inside = tour.places.mapNotNull { place ->
                val current = place.id == state.inside
                val distance = distance(position, place.center)
                if (distance > place.radius * if (current) STAY_FACTOR else 1.0) null
                else place to (distance / place.radius - if (current) 0.2 else 0.0)
            }.minByOrNull { it.second }?.first?.id
        } else if (inside != null) {
            val current = tour.places.first { it.id == inside }
            if (distance(position, current.center) > current.radius * STAY_FACTOR + fix.accuracy * tour.pixelsPerMeter) inside = null
        }
        val arrival = if (trigger && inside != null && inside != state.inside) tour.places.first { it.id == inside } else null
        state = TourState(tour.key, if (fix.provider == "gps") "live" else "approximate", position, fix.accuracy, inside = inside, fix = fix)
        return Transition(state, arrival)
    }

    fun inArea(point: Point) = inPolygon(point, tour.area) || distanceToPolygon(point, tour.area) <= tour.buffer

    companion object {
        const val ACCURACY_TRIGGER_METERS = 30.0
        const val STAY_FACTOR = 1.2
        fun distance(a: Point, b: Point) = hypot(a.x - b.x, a.y - b.y)
        fun inPolygon(point: Point, polygon: List<Point>): Boolean {
            var inside = false
            var previous = polygon.last()
            for (current in polygon) {
                if ((current.y > point.y) != (previous.y > point.y) &&
                    point.x < (previous.x - current.x) * (point.y - current.y) / (previous.y - current.y) + current.x) inside = !inside
                previous = current
            }
            return inside
        }
        fun distanceToPolygon(point: Point, polygon: List<Point>): Double {
            var best = Double.POSITIVE_INFINITY
            var previous = polygon.last()
            for (current in polygon) {
                val dx = current.x - previous.x
                val dy = current.y - previous.y
                val length2 = dx * dx + dy * dy
                val t = if (length2 == 0.0) 0.0 else (((point.x - previous.x) * dx + (point.y - previous.y) * dy) / length2).coerceIn(0.0, 1.0)
                best = min(best, hypot(point.x - previous.x - t * dx, point.y - previous.y - t * dy))
                previous = current
            }
            return best
        }
        fun haversine(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
            val radians = PI / 180
            val dp = (lat2 - lat1) * radians
            val dl = (lon2 - lon1) * radians
            val h = sin(dp / 2).pow(2) + cos(lat1 * radians) * cos(lat2 * radians) * sin(dl / 2).pow(2)
            return 6371000 * 2 * asin(sqrt(h.coerceIn(0.0, 1.0)))
        }
    }
}
