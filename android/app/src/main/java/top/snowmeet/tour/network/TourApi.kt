package top.snowmeet.tour.network

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import top.snowmeet.tour.BuildConfig

/** Uses the existing PUBLIC topics API, including its server-side limits and moderation. */
class TourApi(private val visitor: String) {
    fun list(museum: String, place: String): JSONObject = request(museum, place, null)
    fun ask(museum: String, place: String, question: String): JSONObject {
        val clean = question.replace(Regex("\\s+"), " ").trim()
        require(clean.length in 2..100) { "问题请控制在 2–100 字以内。" }
        return request(museum, place, JSONObject().put("question", clean))
    }
    private fun request(museum: String, place: String, body: JSONObject?): JSONObject {
        require(museum.matches(Regex("[a-z0-9_]+")) && place.matches(Regex("[a-z0-9_]+"))) { "无效的景点标识。" }
        val encode = { text: String -> URLEncoder.encode(text, "UTF-8") }
        val url = URL("${BuildConfig.TOUR_ORIGIN}/api/tour/${encode(museum)}/places/${encode(place)}/topics")
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000; connection.readTimeout = 70_000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("X-Visitor", visitor)
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.requestMethod = "POST"; connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val payload = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
            if (status !in 200..299) throw java.io.IOException(payload.optString("message").ifBlank { "接口暂不可用（HTTP $status）。" })
            return payload
        } finally { connection.disconnect() }
    }
}
