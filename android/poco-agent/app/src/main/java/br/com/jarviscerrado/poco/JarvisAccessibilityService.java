package br.com.jarviscerrado.poco;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class JarvisAccessibilityService extends AccessibilityService {
    private static volatile JarvisAccessibilityService instance;
    @Override public void onServiceConnected() { instance = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        // Version 0.1 observes only allowlisted apps. No click automation yet.
    }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { instance = null; super.onDestroy(); }

    public static List<String> visibleText(String allowedPackage) {
        JarvisAccessibilityService service = instance;
        if (service == null) return Collections.emptyList();
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        if (root == null || root.getPackageName() == null ||
                !allowedPackage.contentEquals(root.getPackageName())) return Collections.emptyList();
        List<String> values = new ArrayList<>();
        collect(root, values);
        root.recycle();
        return values;
    }

    private static void collect(AccessibilityNodeInfo node, List<String> values) {
        CharSequence text = node.getText();
        if (text != null && text.length() > 0) values.add(text.toString().trim());
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collect(child, values); child.recycle(); }
        }
    }
}
