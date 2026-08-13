package br.com.jarviscerrado.poco;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.BatteryManager;
import android.os.IBinder;
import android.app.Notification;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

public class AgentService extends Service {
    private ScheduledExecutorService executor;
    public static void start(Context context) {
        context.startForegroundService(new Intent(context, AgentService.class));
    }

    @Override public void onCreate() {
        super.onCreate();
        NotificationChannel channel = new NotificationChannel("jarvis_agent", "Jarvis Poco", NotificationManager.IMPORTANCE_LOW);
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
        Notification notification = new Notification.Builder(this, "jarvis_agent")
            .setContentTitle("Jarvis Poco ativo").setContentText("Conectando ao núcleo no Raspberry Pi")
            .setSmallIcon(android.R.drawable.presence_online).build();
        startForeground(41, notification);
        executor = Executors.newSingleThreadScheduledExecutor();
        executor.scheduleWithFixedDelay(this::cycle, 1, 20, TimeUnit.SECONDS);
    }

    private void cycle() {
        try {
            String endpoint = getSharedPreferences("agent", MODE_PRIVATE).getString("endpoint", "");
            String secret = SecretStore.load(this);
            if (endpoint.isEmpty() || secret.isEmpty()) return;
            ApiClient client = new ApiClient(endpoint, secret);
            client.post("/api/poco/heartbeat", heartbeat());
            JSONObject response = client.get("/api/poco/jobs/next");
            if (!response.isNull("job")) execute(client, response.getJSONObject("job"));
        } catch (Exception ignored) { }
    }

    private JSONObject heartbeat() throws Exception {
        Intent battery = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        int level = battery == null ? -1 : battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
        int temperature = battery == null ? -1 : battery.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1);
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
        boolean wifi = caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI);
        return new JSONObject().put("node_id", "poco-x3-nfc").put("battery_level", level)
            .put("battery_temperature_c", temperature / 10.0).put("thermal_status", "android")
            .put("wifi_connected", wifi).put("agent_version", BuildConfig.VERSION_NAME);
    }

    private void execute(ApiClient client, JSONObject job) throws Exception {
        String id = job.getString("job_id");
        String action = job.getString("action");
        client.state(id, "running", null, null);
        try {
            if (action.equals("device_status")) client.state(id, "completed", heartbeat(), null);
            else if (action.equals("network_check")) {
                ConnectivityManager cm = getSystemService(ConnectivityManager.class);
                NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
                JSONObject result = new JSONObject()
                    .put("wifi_connected", caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))
                    .put("internet_validated", caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED))
                    .put("internet_capable", caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
                client.state(id, "completed", result, null);
            } else if (action.equals("refresh_saneago_bills")) {
                client.state(id, "completed", SaneagoReader.readCurrent(this), null);
            } else client.state(id, "failed", null, "Acao ainda nao implementada no agente 0.1");
        } catch (Exception error) {
            String message = error.getClass().getSimpleName();
            if (error.getMessage() != null) message += ": " + error.getMessage();
            client.state(id, "failed", null, message.substring(0, Math.min(message.length(), 180)));
        }
    }

    @Override public void onDestroy() { if (executor != null) executor.shutdownNow(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent) { return null; }
}
