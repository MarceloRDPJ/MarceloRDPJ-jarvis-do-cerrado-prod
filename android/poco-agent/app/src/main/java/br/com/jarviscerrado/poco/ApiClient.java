package br.com.jarviscerrado.poco;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONObject;

public class ApiClient {
    /** Carries the HTTP status so callers can tell a rejected job from a dead network. */
    static final class HttpException extends Exception {
        final int code;
        HttpException(int code) { super("HTTP " + code); this.code = code; }
        /** 4xx means the Pi will never accept this payload; retrying it forever is pointless. */
        boolean permanent() { return code >= 400 && code < 500; }
    }

    private final String endpoint;
    private final String secret;
    ApiClient(String endpoint, String secret) { this.endpoint = endpoint.replaceAll("/$", ""); this.secret = secret; }

    JSONObject get(String path) throws Exception { return request("GET", path, new byte[0]); }
    JSONObject post(String path, JSONObject payload) throws Exception {
        return request("POST", path, payload.toString().getBytes(StandardCharsets.UTF_8));
    }
    void state(String id, String status, JSONObject result, String error) throws Exception {
        JSONObject payload = new JSONObject().put("status", status);
        if (result != null) payload.put("result", result);
        if (error != null) payload.put("error", error);
        post("/api/poco/jobs/" + id + "/state", payload);
    }

    private JSONObject request(String method, String path, byte[] body) throws Exception {
        String timestamp = Long.toString(System.currentTimeMillis() / 1000L);
        HttpURLConnection connection = (HttpURLConnection)new URL(endpoint + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(10000);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setRequestProperty("X-Poco-Timestamp", timestamp);
        connection.setRequestProperty("X-Poco-Signature", signature(timestamp, method, path, body));
        if (body.length > 0) { connection.setDoOutput(true); connection.getOutputStream().write(body); }
        int code = connection.getResponseCode();
        InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        if (stream != null) {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) output.write(buffer, 0, count);
            stream.close();
        }
        if (code >= 400) throw new HttpException(code);
        return new JSONObject(output.toString(StandardCharsets.UTF_8));
    }

    private String signature(String timestamp, String method, String path, byte[] body) throws Exception {
        String canonical = timestamp + "\n" + method + "\n" + path + "\n" + hex(MessageDigest.getInstance("SHA-256").digest(body));
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return hex(mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
    }
    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte value : bytes) out.append(String.format("%02x", value));
        return out.toString();
    }
}
