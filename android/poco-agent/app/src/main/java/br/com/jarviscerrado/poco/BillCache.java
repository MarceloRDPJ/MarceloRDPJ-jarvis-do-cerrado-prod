package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/**
 * Last confirmed reading per provider and property, encrypted at rest.
 *
 * Driving the official apps takes minutes and can fail for reasons outside our
 * control (session expired, human verification). Keeping the last real reading on
 * the phone lets the Pi answer instantly with something true, as long as it is
 * presented as a dated cache and never as a fresh measurement.
 */
final class BillCache {
    private static final String ALIAS = "rod_poco_bill_cache_v1";
    private static final String PREFS = "bill_cache_secure";

    private BillCache() { }

    static String key(String provider, String property) {
        return provider + ":" + (property == null || property.isEmpty() ? "casa" : property);
    }

    static void store(Context context, String provider, String property, JSONObject result, long now) {
        try {
            JSONObject all = document(context);
            JSONObject entry = new JSONObject(result.toString());
            entry.put("cached_at", now);
            all.put(key(provider, property), entry);
            write(context, all.toString());
        } catch (Exception ignored) {
            // A cache write must never break a successful reading.
        }
    }

    /** Returns the stored reading marked as cached, or throws when there is nothing to offer. */
    static JSONObject read(Context context, String provider, String property, long now) throws Exception {
        JSONObject all = document(context);
        String name = key(provider, property);
        if (!all.has(name))
            throw new IllegalStateException("Ainda nao existe leitura confirmada de " + provider + " para " + property);
        JSONObject entry = all.getJSONObject(name);
        long cachedAt = entry.optLong("cached_at", 0L);
        entry.put("source", "rod_bill_cache");
        entry.put("from_cache", true);
        entry.put("cache_age_seconds", cachedAt == 0 ? -1 : Math.max(0, (now - cachedAt) / 1000L));
        return entry;
    }

    private static JSONObject document(Context context) {
        try {
            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String ciphertext = prefs.getString("ciphertext", "");
            String iv = prefs.getString("iv", "");
            if (ciphertext.isEmpty() || iv.isEmpty()) return new JSONObject();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
            return new JSONObject(new String(cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)), StandardCharsets.UTF_8));
        } catch (Exception ignored) {
            return new JSONObject();
        }
    }

    private static void write(Context context, String json) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(json.getBytes(StandardCharsets.UTF_8));
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
            .apply();
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(
            ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build());
        return generator.generateKey();
    }
}
