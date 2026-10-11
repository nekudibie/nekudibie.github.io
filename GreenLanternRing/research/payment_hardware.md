# Payment hardware research — Approaches B, C, D, E and the decision

**Status:** desk research 2026-10-11. The sandbox could run web searches but could **not open most
supplier and manufacturer pages directly**, so every claim below comes from search-engine extracts of
the cited pages. Claims marked *(verify)* must be confirmed on the official page before money is spent.
Nothing has been purchased or tested yet.

## 0. Key principle: three separate things must all be true

| Layer | What it means | Who controls it |
|---|---|---|
| **Hardware**: a secure element plus antenna that a terminal can power and talk to | ISO 14443 / EMV contactless | Chip and module maker (Infineon, NXP, IDEMIA…) |
| **Certification**: a device type approved by Visa or Mastercard | EMVCo and the network's letter of approval | Device maker |
| **Credential**: a live card number or token, personalised into *that* SE, linked to *your* account | Provisioning by an issuer or token service provider (TSP) | Your bank, or a TSP such as DIGISEQ, Fidesmo, Tappy, or Cash App for its own Tags |

A blank SE (for example an Infineon SECORA Pay chip from a distributor) has the hardware layer only.
Development samples are usually personalised with **test keys**, which live terminals reject.
**Only the third layer makes a device payment-ready**, and only issuers or TSPs can do it.

## 1. The Cash App Wand (your suggestion), and why it points to the right answer

* Launched by Block on 5 June 2026: a $25 NFC accessory, the first "Cash App Tag". It is a battery-free chip
  in a star-shaped wand, linked in the app to the user's Cash App Card, and works wherever Visa contactless
  is accepted ([TechCrunch](https://techcrunch.com/2026/06/04/cash-app-launches-a-wand-for-tap-and-pay/),
  [Digital Transactions](https://www.digitaltransactions.net/cash-app-tags-debut-starting-with-a-wand/),
  [PaymentsJournal](https://www.paymentsjournal.com/cash-app-turns-a-viral-trend-into-a-new-payments-product/)).
* It came from a viral DIY trend in which people **put an entire, unmodified card inside a wand**
  (Becca Bloom, Jan 2026). Cash App's own wand **does not contain a card**; it is a provisioned tag.
* **UK status: not usable.** Cash App reportedly stopped serving UK users on 15 Sep 2024 (verify), and
  Tags need an eligible Cash App Card.
* **The lesson for us.** There are two ways to put payment into an object:
  1. Enclose a whole intact card. This works for a wand, but at 85.6 × 54 mm a card can't fit in a ring.
  2. Use a **small passive tag provisioned by an issuer or TSP and linked to an existing card**. This is
     exactly what we need. **In the UK, the Cash App Tag equivalent is a Curve-linked wearable activated
     through DIGISEQ's Manage-Mii app or through Fidesmo Pay.** That is Approaches C, D and E below.

## 2. UK provisioning platforms (the part that makes it "payment-ready")

| Platform | How it works | UK route | Evidence |
|---|---|---|---|
| **DIGISEQ Manage-Mii** | A white-label app pairs a bank card or prepaid account with a passive wearable; the wearable then pays like a contactless card | Since Mar 2023 **Curve** customers can link a card to a Manage-Mii wearable and pay immediately | [DIGISEQ × Curve](https://digiseq.co.uk/2023/03/21/wearable-tech-pioneer-digiseq-partners-with-curve-to-bring-passive-wearable-payments-to-europe/), [FStech](https://www.fstech.co.uk/fst/Curve_brings_wearable_payments_tech_to_users.php), [AdornPay activation guide](https://www.adornpay.com/en/pages/activate-curve-vimpay-en) |
| **Fidesmo Pay** | Tokenises a supported card onto Fidesmo-enabled devices | UK via **Curve** as a fallback for unsupported banks | [Fidesmo supported banks](https://shop.fidesmo.com/pages/supported-banks), [Fidesmo news](https://fidesmo.com/news/fidesmo-pay-expands-its-reach/) |
| **Tappy Technologies** | Battery-free modules for straps, rings and fobs; brands embed them and consumers personalise them | B2B only; brand customers included Barclays bPay and Timex | [NFCW](https://www.nfcw.com/2020/05/22/366621/tappy-demo-shows-how-brands-can-add-contactless-payments-to-wearables/), [Visa partner directory](https://partner.visa.com/site/partner-directory/tappy.html) |

**Curve dependency risk.** Lloyds Banking Group agreed to buy Curve in late 2025, with completion expected
in H1 2026 ([Retail Banker International](https://www.retailbankerinternational.com/news/lloyds-to-acquire-curve/),
[FinTech Weekly](https://www.fintechweekly.com/magazine/articles/lloyds-confirms-curve-acquisition-investor-governance-dispute)).
I found **no statement on whether Manage-Mii and Fidesmo wearables continue under Lloyds**. This is the
single biggest open risk to the recommended architecture. **Check it in the Curve and Manage-Mii apps
before buying anything** (task P1-03).

Fee note: Curve's current free plan ("Curve Pay", formerly Lite) includes £250 per month of fee-free
spending, with 2.99% above that ([Curve help](https://help.curve.com/en_gb/fees-HkkKBu2Lu.md)). *(Verify
which fees apply to purchases in GBP inside the UK. The fee may only apply to some spend types.)*

## 3. Approach B: buy a pre-provisioned OEM module

| Candidate | Model / format | Size | Antenna | Networks | Sold to individuals? | Live credential path for you? | Verdict |
|---|---|---|---|---|---|---|---|
| **IDEMIA Flybuy Mini FOB** (ex-Oberthur, 2016) | SIM-size insert delivered on an ID-1 card carrier, "with integrated antenna" | ~25 × 15 mm (launch coverage) | Integrated (complete chip and antenna) | Visa and Mastercard certified (IDEMIA page) | **No**: sold to issuers (for example UAE Exchange 2017, Westpac PayWear) | Only through an issuer that runs a Flybuy programme. No UK consumer programme found | **NO-GO** unless the enquiry finds a route ([IDEMIA](https://www.idemia.com/wearable-payment-means), [brochure PDF](https://www.idemia.com/wp-content/uploads/2021/02/wearable-payment-means-brochure-idemia-202102.pdf), [Intelligent CIO](https://www.intelligentcio.com/me/2017/05/14/uae-exchange-launches-wearable-card-using-oberthur-technologies-flybuy-minifob/)) |
| **Infineon SECORA Pay W** (Smart Payment Accessory) | EMV chip, OS, applet and antenna on 35 mm tape; pre-certified by Visa and Mastercard | The distributor brief says module 17.5 × 27.2 × 0.25 mm *(verify; another source mentions a smaller "SPA2.1" antenna)* | Complete inlay; a ferrite variant exists for metal surfaces | Visa and Mastercard | **No**: reel quantities for manufacturers | Needs a TSP or issuer to personalise | **NO-GO** for an individual ([Infineon press](https://infineon.com/cms/en/about-infineon/press/market-news/2018/INFDSS201811-020.html), [Macnica brief](https://www.macnica.co.jp/business/semiconductor/manufacturers/Infineon-product-brief-smart-payment-accessory-PB-v01_00-EN.pdf)) |
| **Universal Smart Cards SmarTap** modules | Mastercard-certified modules "for those who design their own products" | Unknown | Unknown | Mastercard | B2B enquiry | Unknown (must ask) | **Worth one email** ([usmartcards](https://www.usmartcards.co.uk/smartap-genus-inlay)) |
| **Tappy** modules | Ring, strap and fob modules | Unknown | Complete | Visa and Mastercard | B2B, white label | Through the brand's app | NO-GO for individuals |

**Conclusion B:** these are the *right* components, but for issuers and brands rather than for a single
consumer. The IDEMIA enquiry ([`idemia_enquiry.md`](idemia_enquiry.md)) is a cheap, low-probability lead
worth one polite email, and it is not on the critical path.

## 4. Approach C: dismantle a cheap payment fob (snapshot prices)

| Product | Price | Activation | Notes |
|---|---|---|---|
| AdornPay key fob (Curve or VIMpay) | ~$48 | Curve via Manage-Mii | [AdornPay](https://www.adornpay.com/en/products/wearable-keyfob-vegan-leer-black) |
| AdornPay key fob (MuchBetter) | ~$30 | MuchBetter account | Not a card-linked UK bank route |
| K-pay "New York" fob | from £65 | Fidesmo Pay | [K-pay](https://k-pay.com/product/new-york/) |
| Tovi Sorga leather fob | £50 | Pingit (Barclays) | Pingit itself appears to be discontinued, so treat as **stale** |
| Generic £0.34–£9 "NFC fobs/rings" | — | — | **Not payment devices**: NTAG or MIFARE only. Do not buy for payment. |

Risks: the fob's antenna may be a 25–30 mm loop, which won't fit under a ring emblem. Dismantling glued or
welded housings can crack the inlay. Removing it from its case may void the warranty or breach terms.
**Measure first, cut never**: X-ray or torch-inspect and measure the inlay before deciding.

## 5. Approach D (recommended): an intact Curve-linked payment ring as the inner core

Buy the cheapest **Curve or Manage-Mii-compatible ceramic or resin payment ring** in your size. Activate
it in the app and pay with it **unmodified**. Then print the Green Lantern ring as a **shell that encloses
it**: the payment ring becomes the band that touches your finger. The CAD (`payment_mode="core"`) has a
fixed side lip and a printed C-ring retainer, so the core slides out undamaged.

| Item | Evidence |
|---|---|
| NEO Ceramic Payment Ring (ID Cards Direct): "supported with Curve"; list £75, seen on a comparison site at **£25.08** in a sale *(verify)* | [ID Cards Direct](https://www.idcardsdirect.co.uk/neo-payment-rings), [topchoice](https://www.topchoice.co.uk/contactless-payment-ring) |
| CNICK Gen2 £119–£129; McLEAR RingPay 2 historically £60–£120 (its own prepaid wallet, 36-month life) | [CNICK](https://cnick.co.uk/), [NotebookCheck](https://www.notebookcheck.net/McLEAR-RingPay-2-Silver-and-limited-edition-Stealth-models-now-available.765233.0.html) |
| AdornPay rings link to Curve via Manage-Mii; reviews call them good value *(price unverified)* | [Trustpilot](https://uk.trustpilot.com/review/adornpay.nl) |

Why D wins:
* **No modification.** The approved antenna and SE stay as designed and certified.
* **A legitimate activation route** (Curve plus Manage-Mii), with no phone needed at checkout.
* **Fully serviceable**: if the core dies or expires, a new one slides into the same shell.
* Each risk can be tested *before* printing: buy the ring, activate it, make three low-value payments.

Costs of D: a thicker band (about 4 mm total over the finger in v0.1). Ring antennas are also known to
be fussier about orientation than cards; you tap with the palm side or the side of the ring. Expect it.

## 6. Approach E (fallback): an intact flat Curve-linked tag under the emblem

If a **Curve-activatable flat tag, sticker or SIM-size insert** can be bought on its own (examples: LAKS
replaceable bracelet chip ([manual](https://www.manualslib.com/manual/2118018/Laks-Key2pay-Mini.html)),
Westpac-style "keeper" inserts, AdornPay or Manage-Mii stickers), it can sit intact under the lens
(`payment_mode="insert"`, with a ferrite sheet between it and the battery). The emblem then faces the
terminal, so you would pay with a "fist bump". **Availability of a UK-activatable small tag is
unverified**, so this stays a fallback until a specific product and its dimensions are confirmed.

## 7. Decision matrix (re-run `python3 research/decision_matrix.py`)

| Approach | Terminal compatibility (25%) | Activation & continued use (20%) | Cost (20%) | Ring size & comfort (15%) | Technical difficulty, 5 = easy (10%) | Reliability & serviceability (10%) | Weighted /5 | Gate |
|---|---|---|---|---|---|---|---|---|
| D  Intact Curve-linked payment ring as core | 4 | 4 | 3 | 3 | 5 | 4 | **3.75** |  |
| E  Intact Curve-linked flat tag under emblem | 3 | 4 | 4 | 3 | 3 | 4 | **3.50** |  |
| C  Dismantle a Curve-linked payment fob | 4 | 4 | 4 | 2 | 3 | 3 | **3.50** |  |
| B  OEM module (IDEMIA / Infineon / Tappy) | 5 | 1 | 1 | 4 | 3 | 4 | **2.95** | BLOCKED (no provisioning path) |
| A  Transplant chip from own card | 2 | 2 | 5 | 4 | 2 | 1 | **2.80** |  |

Scoring rationale: D's cost is 3 because a ring is £25–£75. E and C rate 4 on cost (about £30–£50) but
lower on size and reliability. A rates 1 on reliability (expiry, reissue, SCA, destructive) and 2 on
activation (contract risk, one live card).

## 8. GO / NO-GO (Phase 1)

| Approach | Decision | Condition to change it |
|---|---|---|
| **D: core ring** | **GO (primary)**, conditional | P1-03: Curve plus Manage-Mii (or Fidesmo) still supports the chosen ring in 2026, post-Lloyds |
| **E: flat tag** | **GO (fallback)**, conditional | A specific UK-activatable tag with known dimensions is found |
| C: fob teardown | HOLD | Only if D and E fail; inspect the inlay size non-destructively first |
| B: OEM module | NO-GO | IDEMIA or USC replies with a consumer-activatable route |
| A: card transplant | NO-GO (primary); optional experiment | The issuer gives written permission and the card is confirmed wire-bonded |

**Is there a demonstrably viable sub-£50 route?** Not yet proven. D is under £50 **only** if the
£25 sale price of a Curve-compatible ring is real and current. Validate that first. Otherwise
the realistic total for a finished ring is about **£65–£115** (see [`../shopping/uk_bom.csv`](../shopping/uk_bom.csv)).
