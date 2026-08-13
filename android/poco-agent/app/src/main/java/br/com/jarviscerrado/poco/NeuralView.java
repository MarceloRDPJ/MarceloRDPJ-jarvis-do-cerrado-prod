package br.com.jarviscerrado.poco;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.View;

public class NeuralView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private float phase = 0f;

    public NeuralView(Context context) { super(context); }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float cx = getWidth() / 2f;
        float cy = getHeight() / 2f;
        float base = Math.min(getWidth(), getHeight()) * 0.16f;
        for (int i = 6; i >= 0; i--) {
            float pulse = (float)Math.sin(phase + i * .55f) * base * .08f;
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2f + i);
            paint.setColor(Color.argb(45 + i * 22, 40, 190 + i * 7, 255));
            canvas.drawCircle(cx, cy, base + i * 12f + pulse, paint);
        }
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(20, 120, 210));
        canvas.drawCircle(cx, cy, base * .72f + (float)Math.sin(phase) * 7f, paint);
        phase += .035f;
        postInvalidateDelayed(50);
    }
}
