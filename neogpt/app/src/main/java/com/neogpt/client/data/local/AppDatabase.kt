package com.neogpt.client.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [ConversationEntity::class, MessageEntity::class],
    version = 1,
    // Room warns "Schema export directory was not provided" unless the processor
    // receives room.schemaLocation. The KSP toolchain used here does not pass the
    // ksp { arg(...) } block through, so export stays off. Once the project is
    // built with Gradle/Android Studio, apply the Room Gradle plugin
    // (id("androidx.room")) + room { schemaDirectory(...) } and flip this back to
    // true together with the first Migration.
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun conversationDao(): ConversationDao
    abstract fun messageDao(): MessageDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                AppDatabase::class.java,
                "neogpt.db",
            ).build().also { instance = it }
        }
    }
}
