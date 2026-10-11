# UK supplier research (status 2026-10-11)

**Method and limitation.** Web search worked from the build environment, but direct access to most
supplier and manufacturer sites was blocked by its network policy. So **no price, stock level or product
page in this project has been confirmed by opening the supplier's site.** Every price in
[`../shopping/uk_bom.csv`](../shopping/uk_bom.csv) is marked `No - estimate` or `search snapshot`,
and its link is a supplier **search** URL, not a guessed product page. Please confirm prices yourself, or
let me re-check from an environment with web access, before ordering.

| Supplier | Good for | Delivery notes (verify) |
|---|---|---|
| Farnell UK (uk.farnell.com) | Kingbright LEDs, BAT54, resistors, ATtiny | Next-day; small-order P&P may apply |
| Mouser UK (mouser.co.uk) | Same | Free delivery above a threshold (historically ~£33); duties included |
| DigiKey UK | Same | Similar to Mouser |
| RS (uk.rs-online.com) | Same, plus tools | Trade-friendly; small-order charge possible |
| Pimoroni / The Pi Hut | Adafruit Micro-Lipo USB-C (#4410), PN532, Pinecil, Raspberry Pi | UK stock; fast |
| 3DJake UK | PETG (black, translucent green, natural) | |
| Amazon UK | Magnet wire, NTAG cards, ferrite sheets, pogo pins, micro screws, slide switches, tiny LiPos | Check seller ratings; insist on a cell datasheet and PCM |
| ID Cards Direct (UK) | NEO ceramic payment ring (Curve-compatible) | Listed £75, sale listing £25.08 seen (verify) |
| AdornPay (NL) | Curve/Manage-Mii rings, fobs, straps | Ships to the UK? (verify) |
| Fidesmo shop | Fidesmo Pay devices | UK via Curve (verify) |

## Things that look like payment devices but aren't

Cheap "NFC rings" on Amazon or eBay (£5–£10) and "NFC key fobs" (£0.34–£1.15) are **NTAG/MIFARE tags**.
They can store a URL; **they cannot pay**. Ignore them for payment and use them only for Phase 2 practice.

## Tiny LiPo cells: buying checklist

1. Datasheet with dimensions, capacity, maximum charge current (C-rate) and PCM thresholds.
2. A PCM is visible (a small board under Kapton at the tab end).
3. Dimensions **including** the PCM fit the CAD envelope (Design B: 12 × 10 × 3.0 mm).
4. UK seller, or a reputable importer. Avoid listings with no brand or datasheet.
