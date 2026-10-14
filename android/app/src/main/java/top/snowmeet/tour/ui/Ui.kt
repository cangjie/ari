package top.snowmeet.tour.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.widget.*

object Ui {
    val background = Color.rgb(243, 242, 242)
    val ink = Color.rgb(35, 32, 29)
    val accent = Color.rgb(107, 79, 29)
    fun dp(context: Context, value: Int) = (context.resources.displayMetrics.density * value).toInt()
    fun card(context: Context, color: Int = Color.WHITE, radius: Int = 16) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(context, radius).toFloat(); setStroke(dp(context, 1), Color.rgb(221, 215, 204))
    }
    fun column(context: Context) = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    fun text(context: Context, text: String, size: Float = 15f, bold: Boolean = false) = TextView(context).apply {
        this.text = text; textSize = size; setTextColor(ink)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setPadding(dp(context, 4), dp(context, 7), dp(context, 4), dp(context, 7))
    }
    fun button(context: Context, label: String, action: () -> Unit) = Button(context).apply {
        text = label; isAllCaps = false; setTextColor(accent); setOnClickListener { action() }
        minHeight = dp(context, 44)
    }
    fun space(context: Context, height: Int) = View(context).apply { layoutParams = LinearLayout.LayoutParams(1, dp(context, height)) }
}

data class Guide(val id: String, val name: String, val glyph: String, val color: Int)
object Guides {
    val all = listOf(Guide("ari", "阿瑞", "瑞", Ui.accent), Guide("xiaoai", "小爱", "爱", Color.rgb(111, 88, 67)))
    fun find(id: String) = all.firstOrNull { it.id == id } ?: all.first()
}
