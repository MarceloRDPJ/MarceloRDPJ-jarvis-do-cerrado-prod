package br.com.jarviscerrado.poco;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    private SharedPreferences preferences;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        preferences = getSharedPreferences("agent", MODE_PRIVATE);
        if (BuildConfig.DEBUG && getIntent().hasExtra("provision_secret")) {
            try {
                String provisionedEndpoint = getIntent().getStringExtra("provision_endpoint");
                String provisionedSecret = getIntent().getStringExtra("provision_secret");
                if (provisionedEndpoint != null && provisionedSecret != null && provisionedSecret.length() >= 32) {
                    preferences.edit().putString("endpoint", provisionedEndpoint).apply();
                    SecretStore.save(this, provisionedSecret);
                    getIntent().removeExtra("provision_secret");
                    AgentService.start(this);
                }
            } catch (Exception ignored) { }
        }
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(36, 30, 36, 30);
        root.setBackgroundColor(Color.BLACK);

        NeuralView neural = new NeuralView(this);
        root.addView(neural, new LinearLayout.LayoutParams(-1, 0, 1f));

        TextView status = new TextView(this);
        status.setTextColor(Color.rgb(130, 225, 255));
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        status.setText("JARVIS // NÓ POCO");
        root.addView(status);

        EditText endpoint = field("Endereço do Pi", preferences.getString("endpoint", "http://192.168.1.10:8000"), false);
        EditText secret = field("Chave do nó", "", true);
        if (!SecretStore.load(this).isEmpty()) secret.setHint("Chave protegida no Android Keystore");
        root.addView(endpoint);
        root.addView(secret);

        Button save = button("Salvar e iniciar");
        save.setOnClickListener(v -> {
            preferences.edit().putString("endpoint", endpoint.getText().toString().trim()).apply();
            try {
                if (secret.getText().length() > 0) SecretStore.save(this, secret.getText().toString());
                AgentService.start(this);
                status.setText("AGENTE INICIADO // AGUARDANDO PI");
            } catch (Exception error) { status.setText("ERRO AO PROTEGER A CHAVE"); }
        });
        root.addView(save);

        Button accessibility = button("Ativar acessibilidade do Jarvis");
        accessibility.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(accessibility);
        setContentView(root);
    }

    private EditText field(String hint, String value, boolean password) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setHintTextColor(Color.GRAY);
        field.setTextColor(Color.WHITE);
        field.setText(value);
        field.setSingleLine(true);
        if (password) field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        field.setLayoutParams(new LinearLayout.LayoutParams(-1, -2));
        return field;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setLayoutParams(new LinearLayout.LayoutParams(-1, -2));
        return button;
    }
}
