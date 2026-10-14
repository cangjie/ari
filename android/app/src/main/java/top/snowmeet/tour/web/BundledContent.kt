package top.snowmeet.tour.web

import android.content.Context
import android.net.Uri
import android.webkit.WebResourceResponse
import java.io.IOException

/** Maps the reserved HTTPS /app/tour/ path to APK assets; API requests stay on the website. */
class BundledContent(private val context: Context) {
    fun intercept(uri: Uri): WebResourceResponse? {
        val path = uri.path ?: return null
        if (!path.startsWith("/app/tour/")) return null
        val asset = path.removePrefix("/app/")
        if (asset.split('/').any { it == ".." || it == "." } || asset.contains('\\')) return failure(403, "Blocked")
        val mime = when (asset.substringAfterLast('.')) {
            "html" -> "text/html"
            "js" -> "application/javascript"
            "css" -> "text/css"
            "json" -> "application/json"
            "svg" -> "image/svg+xml"
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "webp" -> "image/webp"
            "woff2" -> "font/woff2"
            else -> "application/octet-stream"
        }
        return try {
            WebResourceResponse(mime, if (mime.startsWith("text/") || mime in setOf("application/json", "application/javascript", "image/svg+xml")) "UTF-8" else null,
                context.assets.open(asset))
        } catch (_: IOException) { failure(404, "Not Found") }
    }
    private fun failure(code: Int, reason: String) = WebResourceResponse("text/plain", "UTF-8", code, reason, emptyMap(), reason.byteInputStream())
}
