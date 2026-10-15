package top.snowmeet.tour.tour

import org.junit.Assert.*
import org.junit.Test
import java.io.File

class TourDataTest {
    @Test fun parsesEveryServerMuseumFixtureAndEveryPlaceHasActualIntroduction() {
        val data = File("../../web_api/tour/data")
        val files = data.listFiles()?.filter { it.extension == "json" }.orEmpty()
        assertTrue("Source tour data missing", files.isNotEmpty())
        files.forEach { file ->
            val tour = TourData.parse(file.readText(Charsets.UTF_8))
            assertTrue(tour.places.isNotEmpty())
            assertEquals(file.nameWithoutExtension, tour.key)
            assertTrue(tour.places.all { it.introduction.isNotBlank() })
            assertTrue(tour.places.all { tour.projection.project(tour.entranceLat, tour.entranceLon).x.isFinite() })
        }
    }
}
