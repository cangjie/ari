plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }

android {
    namespace = "top.snowmeet.tour"
    compileSdk = 35
    defaultConfig {
        applicationId = "top.snowmeet.tour"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "TOUR_ORIGIN", "\"https://tour.snowmeet.top\"")
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    testOptions { unitTests.isReturnDefaultValues = true }
}
dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
