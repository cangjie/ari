package top.snowmeet.tour.ui

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.ScrollView
import android.widget.Switch
import top.snowmeet.tour.MainActivity
import top.snowmeet.tour.TourRuntime

class CompanionSettings(private val activity: MainActivity) {
    fun show() {
        val prefs = TourRuntime.preferences
        val body = Ui.column(activity).apply { setPadding(Ui.dp(activity, 18), Ui.dp(activity, 8), Ui.dp(activity, 18), Ui.dp(activity, 12)) }
        body.addView(Ui.text(activity, "你的导览员", 18f, true))
        Guides.all.forEach { guide ->
            body.addView(Ui.button(activity, (if (prefs.guide == guide.id) "✓ " else "") + guide.name) {
                prefs.guide = guide.id; TourRuntime.notifyChanged()
                android.widget.Toast.makeText(activity, "已切换为${guide.name}", android.widget.Toast.LENGTH_SHORT).show()
            })
        }
        body.addView(Ui.text(activity, "后台陪伴", 18f, true))
        body.addView(Switch(activity).apply {
            text = "后台定位与到站提醒"; isChecked = prefs.companion
            setOnCheckedChangeListener { _, enabled -> activity.setCompanion(enabled) }
        })
        body.addView(Switch(activity).apply {
            text = "悬浮导览员"; isChecked = prefs.overlay
            setOnCheckedChangeListener { _, enabled ->
                prefs.overlay = enabled
                if (enabled && !Settings.canDrawOverlays(activity)) activity.startActivity(
                    Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${activity.packageName}")))
                TourRuntime.notifyChanged()
            }
        })
        body.addView(Ui.text(activity, "陪伴模式需从 App 内启动；停止后不在后台定位。悬浮头像在切到其它应用后显示，锁屏时使用到站通知。"))
        val fine = activity.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val notifications = Build.VERSION.SDK_INT < 33 || activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        body.addView(Ui.text(activity, "定位：${if (fine) "已允许精确定位" else "未允许精确定位"}\n通知：${if (notifications) "已允许" else "未允许"}\n悬浮窗：${if (Settings.canDrawOverlays(activity)) "已允许" else "未允许"}"))
        body.addView(Ui.button(activity, "申请定位与通知权限") { activity.requestLocation() })
        body.addView(Ui.button(activity, "应用权限与小米后台设置") {
            activity.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${activity.packageName}")))
        })
        body.addView(Ui.text(activity, "小米 / 红米：在应用设置中开启自启动、允许悬浮窗，电池策略选“无限制”；不同 HyperOS / MIUI 版本的入口可能不同。"))
        body.addView(Ui.text(activity, "数据与文字互动", 18f, true))
        body.addView(Ui.text(activity, "定位用于本机到站判定；当前版本尚未连接轨迹上传接口。网页与悬浮窗共用匿名设备号和公开问答接口，提交的问题与回答可能向所有游客公开。没有录音或语音功能。"))
        body.addView(Ui.button(activity, "停止陪伴") { activity.setCompanion(false) })
        AlertDialog.Builder(activity).setTitle("陪伴模式").setView(ScrollView(activity).apply { addView(body) })
            .setPositiveButton("完成", null).show()
    }
}
