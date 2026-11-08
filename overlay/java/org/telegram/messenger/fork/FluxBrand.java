package org.telegram.messenger.fork;

import java.util.regex.Pattern;

/**
 * Telegram downloads language packs from the server, and they override strings.xml
 * (for example AppName = "Telegram"). So patching strings.xml is not enough for non-English UI.
 * LocaleController.getStringInternal(...) is wrapped to pass every string through this class.
 */
public class FluxBrand {

    public static final String NAME = "FluxGram";

    // "Telegram" but not product names that really are Telegram's
    private static final Pattern LATIN = Pattern.compile(
            "Telegram(?! Premium| Business| Stars| Passport| Ads| Web| Desktop| Support| FAQ| Android| Bot| Mini)");
    // Телеграм, Телеграме, Телеграма ... (any ending)
    private static final Pattern CYRILLIC = Pattern.compile("(?iu)телеграм[\\p{L}]*");

    public static String apply(String key, String value) {
        if (value == null) {
            return null;
        }
        if (key != null) {
            if (key.equals("AppName")) {
                return NAME;
            }
            if (key.equals("AppNameBeta")) {
                return NAME + " Beta";
            }
            if (key.endsWith("Url") || key.endsWith("URL") || key.endsWith("Faq") || key.startsWith("Telegram")) {
                return value;
            }
        }
        if (value.indexOf("Telegram") < 0 && value.indexOf("елеграм") < 0) {
            return value;
        }
        String result = LATIN.matcher(value).replaceAll(NAME);
        result = CYRILLIC.matcher(result).replaceAll(NAME);
        return result;
    }
}
