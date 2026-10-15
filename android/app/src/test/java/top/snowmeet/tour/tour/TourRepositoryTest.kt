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
}
