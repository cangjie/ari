package top.snowmeet.tour.tour

import android.content.Context
import org.json.JSONArray
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Latest catalog comes from the live website; disk is only a last-good geofence cache. */
class TourRepository(private val cache: File) {
    constructor(context: Context) : this(File(context.filesDir, "tour-catalog.json"))
    @Volatile var tours: List<TourData> = runCatching { decode(cache.readText(Charsets.UTF_8)) }.getOrDefault(emptyList())
        private set
    @Synchronized fun replace(text: String) {
        val incoming = decode(text)
        cache.parentFile?.mkdirs()
        val temporary = File.createTempFile("catalog-", ".json", cache.parentFile)
        try {
            temporary.writeText(text, Charsets.UTF_8)
            Files.move(temporary.toPath(), cache.toPath(), StandardCopyOption.REPLACE_EXISTING)
            tours = incoming
        } finally { temporary.delete() }
    }
    fun find(key: String?) = tours.firstOrNull { it.key == key }
    companion object {
        fun decode(text: String): List<TourData> {
            val array = JSONArray(text)
            val result = (0 until array.length()).map { TourData.parse(array.getJSONObject(it).toString()) }
            require(result.map { it.key }.distinct().size == result.size) { "Duplicate museum key" }
            require(result.all { it.key.matches(Regex("[a-z0-9_]{1,32}")) }) { "Invalid museum key" }
            return result
        }
    }
}
