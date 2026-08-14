package br.com.jarviscerrado.poco;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.LinkedHashMap;
import java.util.Map;
import org.json.JSONObject;

public final class BillingSettingsActivity extends Activity {
    private final Map<String, EditText> fields = new LinkedHashMap<>();
    private TextView status;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        JSONObject saved;
        try { saved = new JSONObject(EncryptedSettingsStore.load(this)); }
        catch (Exception ignored) { saved = new JSONObject(); }

        LinearLayout content = RodUi.screen(this);

        title(content, "ROD // COFRE DE CONTAS");
        note(content, "Credenciais e unidades ficam criptografadas neste Poco pelo Android Keystore.");

        section(content, "SANEAGO — ACESSO");
        addField(content, saved, "saneago_login", "Login/CPF da Saneago", false, false);
        addField(content, saved, "saneago_password", "Senha da Saneago", true, false);

        section(content, "EQUATORIAL — IDENTIFICAÇÃO");
        addField(content, saved, "equatorial_cpf", "CPF do titular (somente números)", true, true);
        addField(content, saved, "equatorial_birth_date", "Data de nascimento (DD/MM/AAAA)", true, false);

        section(content, "UNIDADES POR IMÓVEL");
        property(content, saved, "kitnet_01", "Kitnet 01");
        property(content, saved, "kitnet_02", "Kitnet 02");
        property(content, saved, "sala_comercial", "Sala comercial");
        property(content, saved, "casa", "Casa");

        status = note(content, "Preencha e toque em salvar.");
        Button save = new Button(this);
        save.setText("Salvar no cofre do ROD");
        save.setAllCaps(false);
        save.setOnClickListener(v -> save());
        content.addView(save, new LinearLayout.LayoutParams(-1, -2));

        Button back = new Button(this);
        back.setText("Voltar ao ROD");
        back.setAllCaps(false);
        back.setOnClickListener(v -> finish());
        content.addView(back, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        setContentView(scroll);
    }

    private void property(LinearLayout root, JSONObject saved, String key, String label) {
        TextView name = note(root, label);
        name.setTextColor(Color.rgb(130, 225, 255));
        addField(root, saved, key + "_energy", "Unidade consumidora de energia", true, true);
        addField(root, saved, key + "_water", "Conta de água", true, true);
    }

    private void addField(LinearLayout root, JSONObject saved, String key, String hint, boolean sensitive, boolean numeric) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setHintTextColor(Color.GRAY);
        field.setTextColor(Color.WHITE);
        field.setSingleLine(true);
        field.setText(saved.optString(key, ""));
        int type = numeric ? InputType.TYPE_CLASS_NUMBER : InputType.TYPE_CLASS_TEXT;
        if (sensitive) type |= numeric
            ? InputType.TYPE_NUMBER_VARIATION_PASSWORD
            : InputType.TYPE_TEXT_VARIATION_PASSWORD;
        field.setInputType(type);
        fields.put(key, field);
        root.addView(field, new LinearLayout.LayoutParams(-1, -2));
    }

    private void save() {
        try {
            JSONObject data = new JSONObject();
            for (Map.Entry<String, EditText> entry : fields.entrySet()) {
                data.put(entry.getKey(), entry.getValue().getText().toString().trim());
            }
            BillingConfig config = new BillingConfig(data.toString());
            if (!config.saneagoReady() || !config.equatorialReady()) {
                status.setText("REVISE // INFORME ACESSOS, CPF/DATA E AO MENOS UMA CONTA DE CADA SERVIÇO");
                status.setTextColor(Color.rgb(245, 158, 11));
                return;
            }
            EncryptedSettingsStore.save(this, data.toString());
            status.setText("SALVO // DADOS PROTEGIDOS PELO ANDROID KEYSTORE");
            status.setTextColor(Color.rgb(80, 230, 150));
        } catch (Exception error) {
            status.setText("ERRO // NÃO FOI POSSÍVEL PROTEGER OS DADOS");
            status.setTextColor(Color.rgb(255, 100, 100));
        }
    }

    private void title(LinearLayout root, String value) {
        TextView view = note(root, value);
        view.setTextSize(22);
        view.setGravity(Gravity.CENTER);
        view.setTextColor(Color.rgb(130, 225, 255));
    }

    private void section(LinearLayout root, String value) {
        TextView view = note(root, "\n" + value);
        view.setTextSize(17);
        view.setTextColor(Color.WHITE);
    }

    private TextView note(LinearLayout root, String value) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(Color.LTGRAY);
        view.setTextSize(14);
        view.setPadding(0, 8, 0, 8);
        root.addView(view, new LinearLayout.LayoutParams(-1, -2));
        return view;
    }
}
