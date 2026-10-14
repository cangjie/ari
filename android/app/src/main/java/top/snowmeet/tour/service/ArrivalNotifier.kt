package top.snowmeet.tour.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import top.snowmeet.tour.MainActivity
import top.snowmeet.tour.R
import top.snowmeet.tour.data.Arrival

class ArrivalNotifier(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    init {
        manager.createNotificationChannel(NotificationChannel("companion", "陪伴模式", NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(NotificationChannel("arrival", "到站提醒", NotificationManager.IMPORTANCE_HIGH))
    }
    fun companion(): Notification = Notification.Builder(context, "companion")
        .setSmallIcon(R.drawable.ic_notification).setContentTitle("Ari Travel · 陪伴中")
        .setContentText("正在使用定位；点此打开导览或停止陪伴")
        .setContentIntent(open()).setOngoing(true)
        .addAction(Notification.Action.Builder(null, "停止陪伴", PendingIntent.getService(context, 1,
            Intent(context, TourService::class.java).setAction(TourService.ACTION_STOP), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)).build())
        .build()
    fun arrival(arrival: Arrival) {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = open(arrival)
        val notification = Notification.Builder(context, "arrival").setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("已到达：${arrival.name}").setContentText("点击查看景点介绍与游客互动")
            .setCategory(Notification.CATEGORY_EVENT).setAutoCancel(true).setContentIntent(open)
            .addAction(Notification.Action.Builder(null, "打开地图", open).build()).build()
        manager.notify((arrival.museum + ":" + arrival.place).hashCode(), notification)
    }
    private fun open(arrival: Arrival? = null) = PendingIntent.getActivity(context,
        arrival?.let { (it.museum + it.place).hashCode() } ?: 0,
        Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra("museum", arrival?.museum).putExtra("place", arrival?.place),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
}
