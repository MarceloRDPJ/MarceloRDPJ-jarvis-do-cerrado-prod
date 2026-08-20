package br.com.jarviscerrado.poco;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Validacao do Pix copia e cola lido do QR da fatura.
 *
 * O payload nao e texto livre: e um BR Code, TLV do padrao EMV QR, com checksum
 * proprio. Isso permite uma garantia forte e barata — ou o payload fecha o CRC,
 * ou ele nao e o Pix daquela fatura.
 *
 * Duas regras que nao se negociam:
 *
 * 1. Nada aqui corrige, completa ou reescreve payload. Um Pix "quase valido"
 *    seria uma ordem de pagamento adulterada com aparencia de oficial; o certo e
 *    falhar e deixar o proprietario abrir o portal.
 * 2. Nenhum metodo desta classe registra o payload, nem parte dele. As mensagens
 *    de erro carregam codigo e, no maximo, tamanho.
 *
 * Classe sem dependencia de Android de proposito: ela roda em teste de JVM.
 */
final class PixPayload {
    /** Tag 00, tamanho 02, valor 01: versao do formato EMV. Todo BR Code comeca assim. */
    static final String FORMAT_PREFIX = "000201";
    /** Identificador do arranjo Pix, com o tamanho 0014 que o precede. */
    static final String PIX_GUI = "0014BR.GOV.BCB.PIX";
    /** Tag 63, tamanho 04: o CRC16 fecha o payload. */
    static final String CRC_TAG = "6304";
    /** Abaixo disso nao cabe nem prefixo, nem GUI, nem chave, nem CRC. */
    static final int MIN_LENGTH = 60;
    /** Acima disso nao e Pix de fatura; e outra coisa lida por engano. */
    static final int MAX_LENGTH = 1024;

    private PixPayload() { }

    /**
     * Devolve o payload exatamente como veio, se ele for um BR Code Pix valido.
     *
     * Nem espaco em branco nas pontas e tolerado: aparar seria modificar o que o
     * banco vai ler, e um QR de fatura nao vem com espaco sobrando.
     */
    static String validate(String raw) {
        if (raw == null || raw.isEmpty())
            throw new IllegalStateException("EQUATORIAL_PIX_NOT_FOUND: nenhum Pix foi lido na tela");
        if (raw.length() < MIN_LENGTH || raw.length() > MAX_LENGTH)
            throw new IllegalStateException(
                "EQUATORIAL_PIX_INVALID: o codigo lido nao tem tamanho de Pix (" + raw.length() + " chars)");
        if (!raw.startsWith(FORMAT_PREFIX))
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: o codigo lido nao e um BR Code");
        if (!raw.contains(PIX_GUI))
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: o BR Code lido nao e do arranjo Pix");
        if (!wellFormed(raw))
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: a estrutura do BR Code esta quebrada");
        requireChecksum(raw);
        return raw;
    }

    /** Verdadeiro quando os campos TLV cobrem o payload inteiro, sem sobra nem falta. */
    static boolean wellFormed(String payload) {
        int index = 0;
        while (index < payload.length()) {
            if (index + 4 > payload.length()) return false;
            if (!isDigits(payload, index, 4)) return false;
            int size = Integer.parseInt(payload.substring(index + 2, index + 4));
            index += 4 + size;
            if (index > payload.length()) return false;
        }
        return index == payload.length();
    }

    /**
     * Confere o CRC16 do BR Code.
     *
     * Variante CRC-16/CCITT-FALSE: polinomio 0x1021, inicial 0xFFFF, sem
     * reflexao. E a unica aceita pelo BACEN. O calculo cobre todo o payload
     * incluindo "6304" e excluindo os quatro digitos do proprio checksum.
     */
    private static void requireChecksum(String payload) {
        int tagAt = payload.length() - 8;
        if (tagAt < 0 || !payload.startsWith(CRC_TAG, tagAt))
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: o BR Code lido nao termina em CRC");
        String declared = payload.substring(payload.length() - 4);
        if (!declared.matches("[0-9A-F]{4}"))
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: o CRC do BR Code nao e hexadecimal");
        String computed = checksum(payload.substring(0, payload.length() - 4));
        if (!computed.equals(declared))
            // Nunca substituir o CRC pelo calculado: o payload seria outro, e o
            // proprietario pagaria algo que a Equatorial nao emitiu.
            throw new IllegalStateException("EQUATORIAL_PIX_INVALID: o CRC do Pix lido nao fecha");
    }

    /** CRC16-CCITT-FALSE em hexadecimal maiusculo de quatro digitos. */
    static String checksum(String value) {
        int crc = 0xFFFF;
        for (byte raw : value.getBytes(StandardCharsets.UTF_8)) {
            crc ^= (raw & 0xFF) << 8;
            for (int bit = 0; bit < 8; bit++) {
                if ((crc & 0x8000) != 0) crc = (crc << 1) ^ 0x1021;
                else crc <<= 1;
                crc &= 0xFFFF;
            }
        }
        return String.format("%04X", crc);
    }

    /**
     * Escolhe o unico QR da tela.
     *
     * Duas leituras iguais sao o mesmo QR visto duas vezes, e isso nao e
     * ambiguidade. Dois conteudos diferentes sao: nesse caso nao ha como saber
     * qual deles pertence a fatura pedida, e adivinhar seria entregar a ordem de
     * pagamento errada.
     */
    static String selectSingle(List<String> rawValues) {
        Set<String> distinct = new LinkedHashSet<>();
        if (rawValues != null)
            for (String value : rawValues) if (value != null && !value.isEmpty()) distinct.add(value);
        if (distinct.isEmpty())
            throw new IllegalStateException("EQUATORIAL_PIX_NOT_FOUND: nenhum QR Code visivel na tela");
        if (distinct.size() > 1)
            throw new IllegalStateException(
                "EQUATORIAL_PIX_AMBIGUOUS: a tela mostra " + distinct.size() + " QR Codes diferentes");
        return new ArrayList<>(distinct).get(0);
    }

    private static boolean isDigits(String value, int from, int length) {
        for (int i = from; i < from + length; i++)
            if (value.charAt(i) < '0' || value.charAt(i) > '9') return false;
        return true;
    }
}
