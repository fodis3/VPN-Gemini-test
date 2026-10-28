// SPDX-License-Identifier: GPL-3.0-or-later
plugins { id("com.android.application"); id("org.jetbrains.kotlin.plugin.compose") }
android {
    namespace = "ru.vpngemini.android"
    compileSdk = 37
    defaultConfig {
        applicationId = "ru.vpngemini.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 40007
        versionName = "4.0.7"
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a", "x86_64") }
    }
    signingConfigs {
        val keystorePath = providers.environmentVariable("VPN_GEMINI_KEYSTORE").orNull
        if (!keystorePath.isNullOrBlank()) {
            create("distribution") {
                storeFile = file(keystorePath)
                storePassword = providers.environmentVariable("VPN_GEMINI_STORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("VPN_GEMINI_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("VPN_GEMINI_KEY_PASSWORD").get()
            }
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("distribution")
            isMinifyEnabled = false
        }
    }
    splits {
        abi {
            isEnable = true
            reset()
            include("armeabi-v7a", "arm64-v8a", "x86_64")
            isUniversalApk = true
        }
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    packaging { jniLibs { useLegacyPackaging = true; keepDebugSymbols += "**/*.so" }; resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    testOptions { unitTests.isIncludeAndroidResources = true }
}
dependencies {
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.material3:material3:1.5.0-alpha22")
    implementation("androidx.compose.material:material-icons-extended:1.7.8")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
    testImplementation("org.robolectric:robolectric:4.16.1")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("com.squareup.okhttp3:okhttp-tls:4.12.0")
    testImplementation("androidx.compose.ui:ui-test-junit4:1.12.0-alpha03")
    debugImplementation("androidx.compose.ui:ui-test-manifest:1.12.0-alpha03")
}
