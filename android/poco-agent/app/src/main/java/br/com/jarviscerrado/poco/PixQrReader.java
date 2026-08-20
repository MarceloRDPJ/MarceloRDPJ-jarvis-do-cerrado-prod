package br.com.jarviscerrado.poco;

import android.graphics.Bitmap;
import com.google.mlkit.vision.barcode.BarcodeScanner;
import com.google.mlkit.vision.barcode.BarcodeScannerOptions;
import com.google.mlkit.vision.barcode.BarcodeScanning;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.common.InputImage;
import java.util.ArrayList;
import java.util.List;

/**
 * Le o QR do Pix da tela e devolve o payload, ou falha.
 *
 * Ligacao fina com o ML Kit de proposito: toda a regra — unicidade, formato,
 * CRC — mora em {@link PixPayload}, que nao depende de Android e por isso e
 * testavel na JVM. Aqui ficam apenas o reconhecedor e a conversao da lista.
 *
 * O reconhecedor e restrito a QR Code. Aceitar outros formatos abriria a porta
 * para ler o codigo de barras da propria fatura e chama-lo de Pix.
 *
 * O payload nunca e registrado. A trilha diz se algo foi lido e nada mais.
 */
final class PixQrReader {

    interface Callback {
        void onPayload(String payload);
        void onError(String message);
    }

    private PixQrReader() { }

    static void decode(Bitmap bitmap, Callback callback) {
        BarcodeScannerOptions options = new BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build();
        final BarcodeScanner scanner = BarcodeScanning.getClient(options);
        scanner.process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener(barcodes -> {
                try {
                    List<String> values = new ArrayList<>();
                    for (Barcode code : barcodes) {
                        String raw = code.getRawValue();
                        if (raw != null) values.add(raw);
                    }
                    RodLog.found("pix", "qr na tela", !values.isEmpty());
                    callback.onPayload(PixPayload.validate(PixPayload.selectSingle(values)));
                } catch (RuntimeException error) {
                    callback.onError(error.getMessage());
                } finally {
                    scanner.close();
                }
            })
            .addOnFailureListener(error -> {
                scanner.close();
                callback.onError("EQUATORIAL_PIX_NOT_FOUND: leitor de QR indisponivel ("
                    + error.getClass().getSimpleName() + ")");
            });
    }
}
