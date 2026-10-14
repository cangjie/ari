package top.snowmeet.tour.tour

import org.junit.Assert.*
import org.junit.Test

class GeofenceEngineTest {
    private val tour = TourData("sample", "示例景区", Projection(0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        1.0, listOf(Point(-100.0, -80.0), Point(100.0, -80.0), Point(100.0, 80.0), Point(-100.0, 80.0)),
        30.0, Point(-90.0, 0.0), 0.0, -90.0,
        listOf(Place("hall", "大厅", Point(0.0, 0.0), 10.0, "介绍"), Place("garden", "花园", Point(25.0, 0.0), 20.0, "介绍")))
    private fun fix(x: Double, y: Double = 0.0, accuracy: Double = 5.0, provider: String = "gps") = Fix(y, x, accuracy, 1, provider)

    @Test fun enteringOnceAndExitHysteresis() {
        val engine = GeofenceEngine(tour)
        assertEquals("hall", engine.onFix(fix(0.0)).arrival?.id)
        assertNull(engine.onFix(fix(1.0)).arrival)
        assertEquals("hall", engine.onFix(fix(-11.0)).state.inside)
        assertNull(engine.onFix(fix(-13.0)).state.inside)
        assertEquals("hall", engine.onFix(fix(0.0)).arrival?.id)
    }
    @Test fun overlappingZonesPreferRelativeDistanceAndRetainCurrentZone() {
        val engine = GeofenceEngine(tour)
        engine.onFix(fix(0.0))
        assertEquals("hall", engine.onFix(fix(8.0)).state.inside)
        assertEquals("garden", engine.onFix(fix(18.0)).arrival?.id)
    }
    @Test fun inaccurateFixCannotEnterAndOnlyClearsAfterUncertaintyMargin() {
        val engine = GeofenceEngine(tour)
        assertNull(engine.onFix(fix(0.0, accuracy = 31.0)).state.inside)
        engine.onFix(fix(0.0))
        assertEquals("hall", engine.onFix(fix(-40.0, accuracy = 31.0)).state.inside)
        assertNull(engine.onFix(fix(-44.0, accuracy = 31.0)).state.inside)
    }
    @Test fun networkLocationNeverTriggersArrival() {
        val transition = GeofenceEngine(tour).onFix(fix(0.0, provider = "network"))
        assertNull(transition.arrival)
        assertNull(transition.state.inside)
        assertEquals("approximate", transition.state.status)
    }
    @Test fun transientErrorRetainsZoneWithoutDuplicateArrival() {
        val engine = GeofenceEngine(tour)
        engine.onFix(fix(0.0))
        assertEquals("hall", engine.error("timeout").inside)
        assertNull(engine.onFix(fix(0.0)).arrival)
    }
    @Test fun boundaryBufferAndOutsideReset() {
        val engine = GeofenceEngine(tour)
        engine.onFix(fix(0.0))
        assertTrue(engine.inArea(Point(120.0, 0.0)))
        assertFalse(engine.inArea(Point(131.0, 0.0)))
        val outside = engine.onFix(fix(-131.0)).state
        assertEquals("outside", outside.status)
        assertNull(outside.inside)
        assertEquals(tour.entrance, outside.position)
    }
    @Test fun invalidFixIsRejected() {
        assertThrows(IllegalArgumentException::class.java) { Fix(Double.NaN, 0.0, 5.0, 1) }
        assertThrows(IllegalArgumentException::class.java) { Fix(0.0, 0.0, -1.0, 1) }
    }
}
