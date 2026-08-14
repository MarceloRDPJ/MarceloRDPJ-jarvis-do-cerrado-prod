package br.com.jarviscerrado.poco;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.graphics.Path;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import org.json.JSONObject;

public class JarvisAccessibilityService extends AccessibilityService {
    static final String ACTION_BRIDGE = "br.com.jarviscerrado.poco.ACCESSIBILITY_BRIDGE";
    static final String PREFS_BRIDGE = "accessibility_bridge";
    private static final String SANEAGO = "br.com.saneago";
    private static final String CHROME = "com.android.chrome";

    private final BroadcastReceiver bridge = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            String request = intent.getStringExtra("request_id");
            String operation = intent.getStringExtra("operation");
            if (request == null || operation == null) return;
            try {
                if (operation.equals("open_saneago")) {
                    bringSaneagoToFront(request);
                } else if (operation.equals("read_saneago")) {
                    if (Build.VERSION.SDK_INT >= 31) performGlobalAction(GLOBAL_ACTION_DISMISS_NOTIFICATION_SHADE);
                    new Handler(Looper.getMainLooper()).postDelayed(() -> readSaneagoWithFallback(request), 1800);
                } else if (operation.equals("login_saneago")) {
                    loginSaneago(request, intent.getStringExtra("login"), intent.getStringExtra("password"));
                } else if (operation.equals("open_equatorial")) {
                    Intent browser = new Intent(Intent.ACTION_VIEW, Uri.parse("https://go.equatorialenergia.com.br/"));
                    browser.setPackage(CHROME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(browser);
                    reply(request, true, new JSONObject().put("opened", true), null);
                } else if (operation.equals("fill_equatorial")) {
                    fillEquatorial(request, intent.getStringExtra("cpf"), intent.getStringExtra("birth"), intent.getStringExtra("unit"));
                } else if (operation.equals("read_equatorial")) {
                    readEquatorial(request);
                } else reply(request, false, null, "Operacao nao permitida");
            } catch (Exception error) {
                reply(request, false, null, error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        IntentFilter filter = new IntentFilter(ACTION_BRIDGE);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(bridge, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(bridge, filter);
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { unregisterReceiver(bridge); super.onDestroy(); }

    private void bringSaneagoToFront(String request) {
        performGlobalAction(GLOBAL_ACTION_HOME);
        startActivity(new Intent(this, WakeActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            try {
                Intent launch = getPackageManager().getLaunchIntentForPackage(SANEAGO);
                if (launch == null) throw new IllegalStateException("Saneago nao instalado");
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                startActivity(launch);
                reply(request, true, new JSONObject().put("opened", true), null);
            } catch (Exception error) {
                reply(request, false, null, error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }, 1500);
    }

    private void loginSaneago(String request, String login, String password) {
        if (login == null || password == null || login.isEmpty() || password.isEmpty()) {
            reply(request, false, null, "Credenciais Saneago ausentes no cofre");
            return;
        }
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) { reply(request, false, null, "Tela de login Saneago nao encontrada"); return; }
        List<AccessibilityNodeInfo> editors = new ArrayList<>();
        collectEditors(root, editors);
        if (editors.size() < 2) {
            root.recycle();
            reply(request, false, null, "Campos de login Saneago nao estao acessiveis nesta tela");
            return;
        }
        setNodeText(editors.get(0), login);
        setNodeText(editors.get(1), password);
        boolean clicked = clickFirst(root, "entrar", "acessar", "login");
        for (AccessibilityNodeInfo editor : editors) editor.recycle();
        root.recycle();
        reply(request, clicked, new JSONObject(), clicked ? null : "Botao de entrada Saneago nao encontrado");
    }

    private void fillEquatorial(String request, String cpf, String birth, String unit) {
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) { reply(request, false, null, "Portal Equatorial nao encontrado no Chrome"); return; }
        List<AccessibilityNodeInfo> editors = new ArrayList<>();
        collectEditors(root, editors);
        if (editors.size() < 2) {
            root.recycle();
            reply(request, false, null, "Campos Equatorial indisponiveis ou verificacao humana ativa");
            return;
        }
        String[] values = editors.size() >= 3 ? new String[]{cpf, birth, unit} : new String[]{cpf, unit};
        for (int i = 0; i < values.length && i < editors.size(); i++) setNodeText(editors.get(i), values[i] == null ? "" : values[i]);
        boolean clicked = clickFirst(root, "continuar", "consultar", "entrar", "avancar");
        for (AccessibilityNodeInfo editor : editors) editor.recycle();
        root.recycle();
        reply(request, clicked, new JSONObject(), clicked ? null : "Botao de consulta Equatorial nao encontrado");
    }

    private void readEquatorial(String request) {
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) { reply(request, false, null, "Portal Equatorial nao encontrado"); return; }
        List<String> values = new ArrayList<>();
        collect(root, values);
        root.recycle();
        try {
            Map<String,String> parsed = EquatorialTextParser.parse(String.join("\n", values));
            JSONObject result = new JSONObject().put("source", "equatorial_chrome_accessibility");
            for (Map.Entry<String,String> entry : parsed.entrySet()) result.put(entry.getKey(), entry.getValue());
            reply(request, true, result, null);
        } catch (Exception error) { reply(request, false, null, error.getMessage()); }
    }

    private static void collectEditors(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> result) {
        if (node.isEditable() || "android.widget.EditText".contentEquals(node.getClassName()))
            result.add(AccessibilityNodeInfo.obtain(node));
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collectEditors(child, result); child.recycle(); }
        }
    }

    private static void setNodeText(AccessibilityNodeInfo node, String value) {
        android.os.Bundle arguments = new android.os.Bundle();
        arguments.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);
    }

    private static boolean clickFirst(AccessibilityNodeInfo node, String... labels) {
        String value = ((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription())).toLowerCase();
        for (String label : labels) if (value.contains(label) && node.isClickable())
            return node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = clickFirst(child, labels);
                child.recycle();
                if (clicked) return true;
            }
        }
        return false;
    }

    private JSONObject readSaneago() throws Exception {
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) throw new IllegalStateException("Janela Saneago nao encontrada");
        List<String> text = new ArrayList<>();
        collect(root, text);
        root.recycle();
        JSONObject result = new JSONObject()
            .put("source", "saneago_android_app")
            .put("account", valueAfterPrefix(text, "Conta:"))
            .put("amount", valueAfter(text, "Fatura atual"))
            .put("reference", valueAfter(text, "Referencia", "Referência"))
            .put("due_date", valueAfter(text, "Vencimento"))
            .put("consumption", valueAfter(text, "Consumo"))
            .put("read_only", true);
        if (result.getString("account").isEmpty() || result.getString("amount").isEmpty() ||
                result.getString("reference").isEmpty() || result.getString("due_date").isEmpty() ||
                result.getString("consumption").isEmpty())
            throw new IllegalStateException("Campos financeiros ainda indisponiveis");
        return result;
    }

    private void readSaneagoWithFallback(String request) {
        try {
            reply(request, true, readSaneago(), null);
        } catch (Exception ignored) {
            readSaneagoOcr(request);
        }
    }

    private void readSaneagoOcr(String request) {
        readSaneagoOcr(request, true);
    }

    private void readSaneagoOcr(String request, boolean allowLoginRecovery) {
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult screenshot) {
                HardwareBuffer buffer = screenshot.getHardwareBuffer();
                ColorSpace colorSpace = screenshot.getColorSpace();
                Bitmap hardware = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
                if (hardware == null) {
                    buffer.close();
                    reply(request, false, null, "Screenshot sem bitmap");
                    return;
                }
                Bitmap bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false);
                buffer.close();
                TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                    .process(InputImage.fromBitmap(bitmap, 0))
                    .addOnSuccessListener(text -> {
                        if (allowLoginRecovery && clickLoginRecovery(text)) {
                            bitmap.recycle();
                            new Handler(Looper.getMainLooper()).postDelayed(
                                () -> readSaneagoOcr(request, false), 8000
                            );
                            return;
                        }
                        String normalized = text.getText() == null ? "" : text.getText().toLowerCase();
                        if (!allowLoginRecovery && normalized.contains("abrir tela de login")) {
                            bitmap.recycle();
                            reply(request, false, null, "Sessao Saneago expirada; refaca o login no app oficial");
                            return;
                        }
                        try { reply(request, true, parseOcr(text.getText()), null); }
                        catch (Exception error) {
                            String raw = text.getText() == null ? "" : text.getText();
                            String metrics = " chars=" + raw.length() +
                                " conta=" + raw.toLowerCase().contains("conta") +
                                " fatura=" + raw.toLowerCase().contains("fatura") +
                                " consumo=" + raw.toLowerCase().contains("consumo");
                            reply(request, false, null, error.getMessage() + metrics);
                        }
                        finally { bitmap.recycle(); }
                    })
                    .addOnFailureListener(error -> {
                        bitmap.recycle();
                        reply(request, false, null, "OCR indisponivel: " + error.getClass().getSimpleName());
                    });
            }
            @Override public void onFailure(int errorCode) {
                reply(request, false, null, "Screenshot falhou: " + errorCode);
            }
        });
    }

    private boolean clickLoginRecovery(Text text) {
        for (Text.TextBlock block : text.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                String value = line.getText().toLowerCase();
                Rect bounds = line.getBoundingBox();
                if (bounds != null && value.contains("abrir tela de login")) {
                    Path path = new Path();
                    path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
                    GestureDescription gesture = new GestureDescription.Builder()
                        .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build();
                    return dispatchGesture(gesture, null, null);
                }
            }
        }
        return false;
    }

    static JSONObject parseOcr(String raw) throws Exception {
        Map<String, String> values = SaneagoOcrParser.parse(raw);
        JSONObject result = new JSONObject().put("source", "saneago_android_ocr").put("read_only", true);
        for (Map.Entry<String, String> entry : values.entrySet()) result.put(entry.getKey(), entry.getValue());
        return result;
    }

    private AccessibilityNodeInfo saneagoRoot() {
        return packageRoot(SANEAGO);
    }

    private AccessibilityNodeInfo packageRoot(String packageName) {
        AccessibilityNodeInfo active = getRootInActiveWindow();
        if (belongsTo(active, packageName)) return active;
        if (active != null) active.recycle();
        for (AccessibilityWindowInfo window : getWindows()) {
            AccessibilityNodeInfo root = window.getRoot();
            if (belongsTo(root, packageName)) return root;
            if (root != null) root.recycle();
        }
        return null;
    }

    private static boolean belongsToSaneago(AccessibilityNodeInfo root) {
        return belongsTo(root, SANEAGO);
    }

    private static boolean belongsTo(AccessibilityNodeInfo root, String packageName) {
        return root != null && root.getPackageName() != null && packageName.contentEquals(root.getPackageName());
    }

    private void reply(String request, boolean ok, JSONObject payload, String error) {
        getSharedPreferences(PREFS_BRIDGE, MODE_PRIVATE).edit()
            .putString("request_id", request).putBoolean("ok", ok)
            .putString("payload", payload == null ? "{}" : payload.toString())
            .putString("error", error == null ? "" : error.substring(0, Math.min(error.length(), 180))).apply();
    }

    private static void collect(AccessibilityNodeInfo node, List<String> values) {
        CharSequence text = node.getText();
        if (text != null && text.length() > 0) values.add(text.toString().trim());
        CharSequence description = node.getContentDescription();
        if (description != null && description.length() > 0) values.add(description.toString().trim());
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collect(child, values); child.recycle(); }
        }
    }
    private static String valueAfterPrefix(List<String> values, String prefix) {
        for (String value : values) if (value.startsWith(prefix)) return value.substring(prefix.length()).trim();
        return "";
    }
    private static String valueAfter(List<String> values, String... labels) {
        for (int i = 0; i < values.size() - 1; i++)
            for (String label : labels) if (values.get(i).equalsIgnoreCase(label)) return values.get(i + 1);
        return "";
    }
}
