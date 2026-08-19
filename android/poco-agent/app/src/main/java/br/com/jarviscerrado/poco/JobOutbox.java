package br.com.jarviscerrado.poco;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import java.util.ArrayList;
import java.util.List;

/**
 * Persistent result queue for the Poco node.
 *
 * A bill query can take minutes and the Wi-Fi may drop right after the reading
 * finishes. Without this, the result would die inside the HTTP exception and the
 * Pi would report a timeout for work the phone actually completed. Results are
 * durable here until the Pi acknowledges them, and every executed job_id is
 * remembered so a requeued job is never run twice.
 */
final class JobOutbox extends SQLiteOpenHelper {
    private static final int VERSION = 1;
    private static final long SEEN_RETENTION_MILLIS = 6L * 60 * 60 * 1000;

    static final class Entry {
        final String jobId;
        final String status;
        final String payload;
        final String error;
        final int attempts;
        Entry(String jobId, String status, String payload, String error, int attempts) {
            this.jobId = jobId; this.status = status; this.payload = payload;
            this.error = error; this.attempts = attempts;
        }
    }

    JobOutbox(Context context) { super(context, "rod_outbox.db", null, VERSION); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE outbox (job_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
            + "payload TEXT, error TEXT, created_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE TABLE seen (job_id TEXT PRIMARY KEY, finished_at INTEGER NOT NULL)");
    }

    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        db.execSQL("DROP TABLE IF EXISTS outbox");
        db.execSQL("DROP TABLE IF EXISTS seen");
        onCreate(db);
    }

    /** Stores a terminal result durably. Called before any network attempt. */
    synchronized void record(String jobId, String status, String payload, String error, long now) {
        ContentValues values = new ContentValues();
        values.put("job_id", jobId);
        values.put("status", status);
        values.put("payload", payload);
        values.put("error", error);
        values.put("created_at", now);
        values.put("attempts", 0);
        SQLiteDatabase db = getWritableDatabase();
        db.insertWithOnConflict("outbox", null, values, SQLiteDatabase.CONFLICT_REPLACE);
        ContentValues handled = new ContentValues();
        handled.put("job_id", jobId);
        handled.put("finished_at", now);
        db.insertWithOnConflict("seen", null, handled, SQLiteDatabase.CONFLICT_REPLACE);
    }

    synchronized List<Entry> pending(int limit) {
        List<Entry> entries = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().query("outbox",
                new String[]{"job_id", "status", "payload", "error", "attempts"},
                null, null, null, null, "created_at ASC", Integer.toString(limit))) {
            while (cursor.moveToNext())
                entries.add(new Entry(cursor.getString(0), cursor.getString(1),
                    cursor.getString(2), cursor.getString(3), cursor.getInt(4)));
        }
        return entries;
    }

    synchronized void delivered(String jobId) {
        getWritableDatabase().delete("outbox", "job_id = ?", new String[]{jobId});
    }

    synchronized void failedAttempt(String jobId) {
        getWritableDatabase().execSQL(
            "UPDATE outbox SET attempts = attempts + 1 WHERE job_id = ?", new Object[]{jobId});
    }

    /** True when this job_id already ran, so a requeue by the Pi never double-executes. */
    synchronized boolean alreadyHandled(String jobId) {
        try (Cursor cursor = getReadableDatabase().query("seen", new String[]{"job_id"},
                "job_id = ?", new String[]{jobId}, null, null, null, "1")) {
            return cursor.moveToNext();
        }
    }

    synchronized int pendingCount() {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM outbox", null)) {
            return cursor.moveToNext() ? cursor.getInt(0) : 0;
        }
    }

    synchronized void prune(long now) {
        getWritableDatabase().delete("seen", "finished_at < ?",
            new String[]{Long.toString(now - SEEN_RETENTION_MILLIS)});
    }
}
