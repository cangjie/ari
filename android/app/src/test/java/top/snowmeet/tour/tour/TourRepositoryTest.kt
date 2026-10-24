package top.snowmeet.tour.tour

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** 景区增减排序由在线页面同步；缓存损坏或同步失败不能破坏旧的可用快照。 */
class TourRepositoryTest {
    private fun source(key: String) = JSONObject(File("../../web_api/tour/data/$key.json").readText())

    @Test fun serverOrderAdditionsAndRemovalsReplaceTheWholeCatalog() {
        val cache = Files.createTempDirectory("ari-catalog").resolve("catalog.json").toFile()
        try {
            val repo = TourRepository(cache)
            assertTrue(repo.tours.isEmpty())
            repo.replace(JSONArray().put(source("wmhg")).toString())
            assertEquals(listOf("wmhg"), repo.tours.map { it.key })
            repo.replace(JSONArray().put(source("wanping")).put(source("wmhg")).toString())
            assertEquals(listOf("wanping", "wmhg"), repo.tours.map { it.key })
            assertEquals(repo.tours, TourRepository(cache).tours)
            repo.replace(JSONArray().put(source("wanping")).toString())
            assertNull(repo.find("wmhg"))
            repo.replace("[]")
            assertTrue(TourRepository(cache).tours.isEmpty())
        } finally { cache.parentFile?.deleteRecursively() }
    }

    @Test fun invalidOrDuplicateServerDataDoesNotReplaceGoodCache() {
        val cache = Files.createTempDirectory("ari-catalog").resolve("catalog.json").toFile()
        try {
            val repo = TourRepository(cache)
            repo.replace(JSONArray().put(source("wmhg")).toString())
            val before = cache.readText()
            for (bad in listOf("oops", "[{}]", JSONArray().put(source("wmhg")).put(source("wmhg")).toString())) {
                assertTrue(runCatching { repo.replace(bad) }.isFailure)
                assertEquals(listOf("wmhg"), repo.tours.map { it.key })
                assertEquals(before, cache.readText())
            }
        } finally { cache.parentFile?.deleteRecursively() }
    }

    @Test fun collectionGpsPayloadUsesExistingParserAndAccuracyGate() {
        val root = source("nanluo_shichahai")
        val nav = root.getJSONObject("navigation")
        // Same wire shape sent by app.js nativeTour; production parser stays unchanged.
        for (key in listOf("area", "entrance", "places")) root.put(key, nav.get(key))
        val tours = TourRepository.decode(JSONArray().put(source("wmhg")).put(source("wanping")).put(root).toString())
        val tour = tours.last()
        assertEquals("nanluo_shichahai", tour.key)
        assertEquals(21, tour.places.size)
        val point = nav.getJSONArray("places").getJSONObject(0)
        val engine = GeofenceEngine(tour)
        fun fix(accuracy: Double, provider: String = "gps") = Fix(point.getDouble("lat"), point.getDouble("lon"), accuracy, 1, provider)
        assertNull(engine.onFix(fix(40.0)).arrival)
        assertNull(engine.onFix(fix(5.0, "network")).arrival)
        val arrival = engine.onFix(fix(5.0)).arrival
        assertEquals(point.getString("id"), arrival?.id)
        assertTrue(arrival!!.name.endsWith("附近"))
        assertNull(engine.onFix(fix(5.0)).arrival)
        assertEquals("outside", engine.onFix(Fix(39.9163, 116.3972, 5.0, 2)).state.status)
    }
}
