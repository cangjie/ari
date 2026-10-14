package top.snowmeet.tour.tour

import android.content.Context

class TourRepository(context: Context) {
    val tours: List<TourData> = context.assets.list("tour/data").orEmpty()
        .filter { it.endsWith(".json") }.sorted().map { name ->
            context.assets.open("tour/data/$name").bufferedReader(Charsets.UTF_8).use { TourData.parse(it.readText()) }
        }
    init { require(tours.isNotEmpty()) { "No bundled tour data" }; require(tours.map { it.key }.distinct().size == tours.size) }
    fun find(key: String?) = tours.firstOrNull { it.key == key }
}
