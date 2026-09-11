# WebApp language-switch verification

Tested locally on the current `product_form.html` with the initial URL language `ar`.

| Active language | Minimum order label | Stock label | Dimension labels | Result |
|---|---|---|---|---|
| Arabic | الحد الأدنى للطلب | كمية المخزون | الطول/العرض/الارتفاع/الوزن | Pass |
| Turkish | Minimum Sipariş Miktarı | Stok Miktarı | Uzunluk/Genişlik/Yükseklik/Ağırlık | Pass |
| English | Minimum Order Quantity | Stock Quantity | Length/Width/Height/Weight | Pass |

The test also confirmed that the related placeholders, optional tags, product-code and notes labels, post-language labels, information card, header, and save button update immediately without page reload.

The former failure was caused by `label-minqty` and `label-stock` being nested spans. The previous translation helper updated only direct text nodes of the parent card, leaving those nested spans in Arabic. Both labels now carry explicit translation keys and are updated by the shared live translation routine.

## Dynamic controls

A local dynamic dropdown and boolean attribute were rendered after switching to English. Their fixed UI text was verified as:

- dropdown placeholder: `— Select —`
- boolean labels: `Yes` / `No`
- required-field error: `This field is required`

This confirms the dynamic control text now reads the active language instead of the original URL language.

After switching the same rendered controls live:

| Active language | Minimum-order label | Dropdown placeholder | Boolean labels | Required error |
|---|---|---|---|---|
| Arabic | الحد الأدنى للطلب | — اختر — | نعم / لا | هذا الحقل مطلوب |
| Turkish | Minimum Sipariş Miktarı | — Seçin — | Evet / Hayır | Bu alan zorunludur |

The values were inspected after live language changes, not after page reloads.

## Bot and Webhook notification audit

The user-facing message audit found no direct Arabic literal in a Telegram reply or Webhook notification after the localization pass. The only remaining direct reply literal is the language-neutral `✍️` marker used when the manual text-entry keyboard is opened.

Webhook notification tests were run for Arabic, Turkish, and English. Product-approval and supplier-rejection notices used the stored recipient language and retained dynamic product, company, supplier, reply, and reason values.

All locale files now expose the same 67 translation keys. This prevents a Turkish user from falling back to Arabic or English for a missing fixed label.
