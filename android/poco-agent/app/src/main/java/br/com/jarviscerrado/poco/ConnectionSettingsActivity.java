package br.com.jarviscerrado.poco;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class ConnectionSettingsActivity extends Activity {
    @Override protected void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        LinearLayout root = RodUi.screen(this);
        root.addView(RodUi.label(this, "ROD // CONEXÃO SEGURA"));
        TextView title = RodUi.text(this, "Raspberry Pi", 28, Color.WHITE, true);
        title.setPadding(0, RodUi.dp(this, 8), 0, RodUi.dp(this, 18)); root.addView(title);
        LinearLayout card = RodUi.card(this);
        EditText endpoint = field("Endereço do Pi", false);
        endpoint.setText(getSharedPreferences("agent", MODE_PRIVATE).getString("endpoint", "http://192.168.1.10:8000"));
        EditText secret = field("Nova chave do nó (opcional)", true);
        if (!SecretStore.load(this).isEmpty()) secret.setHint("Chave atual protegida no Keystore");
        card.addView(endpoint); card.addView(secret);
        TextView state = RodUi.text(this, "A chave nunca aparece novamente depois de salva.", 13, RodUi.MUTED, false); card.addView(state);
        Button save = new Button(this); save.setText("Salvar e conectar"); save.setAllCaps(false);
        save.setOnClickListener(v -> { try {
            getSharedPreferences("agent", MODE_PRIVATE).edit().putString("endpoint", endpoint.getText().toString().trim()).apply();
            if (secret.length() > 0) SecretStore.save(this, secret.getText().toString());
            AgentService.start(this); state.setText("CONEXÃO SALVA // AGENTE ATIVO"); state.setTextColor(RodUi.GREEN);
        } catch (Exception e) { state.setText("NÃO FOI POSSÍVEL PROTEGER A CHAVE"); state.setTextColor(RodUi.RED); }});
        card.addView(save); root.addView(card, RodUi.cardParams(this));
        ScrollView scroll = new ScrollView(this); scroll.addView(root); setContentView(scroll);
    }
    private EditText field(String hint, boolean password) {
        EditText f = new EditText(this); f.setHint(hint); f.setHintTextColor(Color.GRAY); f.setTextColor(Color.WHITE); f.setSingleLine(true);
        if (password) f.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD); return f;
    }
}
