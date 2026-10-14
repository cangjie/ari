package top.snowmeet.tour.tour

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Replays states generated from the actual browser geolocation path, never a duplicate test algorithm. */
class GeofenceFixtureTest {
    @Test fun browserSequenceMatchesNativeEngine() {
        val root = JSONObject(File("../testdata/geofence_cases.json").readText(Charsets.UTF_8))
        val key = root.getString("museum")
        val engine = GeofenceEngine(TourData.parse(File("../../web_api/tour/data/$key.json").readText(Charsets.UTF_8)))
        root.getJSONArray("cases").objects().forEachIndexed { i, test ->
            val expected = test.getJSONObject("expected")
            val state = if (test.has("error")) engine.error(test.getString("error"))
            else engine.onFix(Fix(test.getDouble("lat"), test.getDouble("lon"), test.getDouble("acc"), i.toLong())).state
            assertEquals("case $i status", expected.getString("status"), state.status)
            assertEquals("case $i inside", if (expected.isNull("inside")) null else expected.getString("inside"), state.inside)
            assertEquals("case $i x", expected.getDouble("x"), state.position.x, 0.001)
            assertEquals("case $i y", expected.getDouble("y"), state.position.y, 0.001)
        }
    }
}
