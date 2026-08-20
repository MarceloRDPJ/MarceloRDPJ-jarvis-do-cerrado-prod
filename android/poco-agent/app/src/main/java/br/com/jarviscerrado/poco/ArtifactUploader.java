package br.com.jarviscerrado.poco;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONObject;

/**
 * Envia um artefato binario ao Pi por canal proprio.
 *
 * Por que nao dentro do resultado do job: o resultado e JSON, vai para
 * poco_node.json e fica ao lado de um dashboard sem autenticacao documentada. Um
 * boleto em base64 ali significaria a fatura do proprietario gravada em texto
 * claro, sem prazo.
 *
 * O canal reusa exatamente o HMAC dos outros endpoints do no — assinatura sobre
 * timestamp, metodo, caminho e SHA-256 do corpo — e o corpo e o binario cru. O
 * Pi devolve um identificador opaco; e ele, e nao o arquivo, que viaja no
 * resultado do job.
 *
 * Nada do conteudo entra na trilha: so tamanho e o codigo HTTP.
 */
final class ArtifactUploader {
    static final String PATH = "/api/poco/artifacts";
    private static final Pattern ARTIFACT_ID = Pattern.compile("^[0-9a-f]{32}$");
    private static final int CONNECT_TIMEOUT_MILLIS = 7_000;
    private static final int READ_TIMEOUT_MILLIS = 30_000;

    private ArtifactUploader() { }

    /** Devolve o artifact_id opaco atribuido pelo Pi. */
    static String upload(Context context, byte[] body, String mime, String kind) throws Exception {
        String endpoint = context.getSharedPreferences("agent", Context.MODE_PRIVATE)
            .getString("endpoint", "").replaceAll("/$", "");
        String secret = SecretStore.load(context);
        if (endpoint.isEmpty() || secret.isEmpty())
            throw new IllegalStateException(
                "EQUATORIAL_BOLETO_NOT_SENT: o no nao tem endpoint e segredo configurados");
        if (body == null || body.length == 0)
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: nada para enviar");

        String timestamp = Long.toString(System.currentTimeMillis() / 1000L);
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint + PATH).openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(CONNECT_TIMEOUT_MILLIS);
            connection.setReadTimeout(READ_TIMEOUT_MILLIS);
            connection.setFixedLengthStreamingMode(body.length);
            connection.setRequestProperty("Content-Type", mime);
            connection.setRequestProperty("X-Poco-Artifact-Mime", mime);
            connection.setRequestProperty("X-Poco-Artifact-Kind", kind);
            connection.setRequestProperty("X-Poco-Timestamp", timestamp);
            connection.setRequestProperty("X-Poco-Signature", signature(secret, timestamp, body));
            connection.setDoOutput(true);
            connection.getOutputStream().write(body);

            int code = connection.getResponseCode();
            RodLog.step("artefato", "envio respondeu HTTP " + code + " bytes=" + body.length);
            InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
            String response = read(stream);
            if (code != 200)
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_NOT_SENT: o Pi recusou o artefato (HTTP " + code + ")");
            String artifactId = new JSONObject(response).optString("artifact_id", "");
            if (!ARTIFACT_ID.matcher(artifactId).matches())
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_NOT_SENT: o Pi nao devolveu identificador de artefato");
            return artifactId;
        } finally {
            connection.disconnect();
        }
    }

    private static String signature(String secret, String timestamp, byte[] body) throws Exception {
        String canonical = timestamp + "\n" + "POST" + "\n" + PATH + "\n"
            + hex(MessageDigest.getInstance("SHA-256").digest(body));
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return hex(mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
    }

    private static String read(InputStream stream) throws Exception {
        if (stream == null) return "{}";
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int count;
        while ((count = stream.read(buffer)) != -1) output.write(buffer, 0, count);
        stream.close();
        return output.toString(StandardCharsets.UTF_8.name());
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte value : bytes) out.append(String.format("%02x", value));
        return out.toString();
    }
}
