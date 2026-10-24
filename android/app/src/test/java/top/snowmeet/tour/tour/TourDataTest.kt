package top.snowmeet.tour.tour

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.io.File

class TourDataTest {
    @Test fun parsesEveryServerMuseumFixtureAndEveryPlaceHasActualIntroduction() {
        val data = File("../../web_api/tour/data")
        val files = data.listFiles()?.filter { it.extension == "json" }.orEmpty()
        assertTrue("Source tour data missing", files.isNotEmpty())
        files.forEach { file ->
            val root = JSONObject(file.readText(Charsets.UTF_8))
            if (root.optString("mode") == "collection") {
                val navigation = root.optJSONObject("navigation") ?: return@forEach
                for (key in listOf("area", "entrance", "places")) root.put(key, navigation.get(key))
            }
            val tour = TourData.parse(root.toString())
            assertTrue(tour.places.isNotEmpty())
            assertEquals(file.nameWithoutExtension, tour.key)
            assertTrue(tour.places.all { it.introduction.isNotBlank() })
            assertTrue(tour.places.all { tour.projection.project(tour.entranceLat, tour.entranceLon).x.isFinite() })
        }
    }
}
