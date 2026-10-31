plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.10" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.10" apply false
    // KSP version must carry the Kotlin version it was built for.
    id("com.google.devtools.ksp") version "2.1.10-1.0.31" apply false
}
