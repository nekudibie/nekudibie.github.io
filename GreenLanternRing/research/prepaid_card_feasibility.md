# Task 1 — Can a £5–£15 prepaid/debit card become a payment ring? (Approach A)

**Status:** researched 2026-10-11. **Verdict: NO-GO as the primary architecture. GO only as an
optional, issuer-permitted experiment, after Phase 2 rehearsals on non-payment cards.**

Evidence grades used here: **[D]** demonstrated (a published build that worked), **[E]** experimental
(it worked for some people, inconsistently), **[T]** theoretical, **[U]** unsupported assumption.

---

## 1. How a contactless bank card is built (short lesson)

A contactless EMV card is two things laminated into PVC:

1. **A secure element (SE)**: a tamper-resistant microcontroller that holds the issuer's keys and runs the
   Visa or Mastercard payment applet. It sits in the gold **contact module** (the "chip").
   A dual-interface module talks to card readers through the gold pads (contact mode, ISO 7816) and over
   radio (contactless mode, ISO/IEC 14443 at 13.56 MHz).
2. **An antenna**: a coil of copper running round the card's edge. The reader's 13.56 MHz magnetic
   field induces a voltage in this coil. That voltage powers the chip (the card has no battery) and carries
   the data in both directions.

Cards join the antenna to the chip in one of two ways:

| Construction | How the antenna reaches the chip | Implication for a ring transplant |
|---|---|---|
| **Wire-bonded / direct-connect** | The card-body coil is soldered or pressed onto two pads on the back of the module | A new coil can be connected to those two pads. This is what the Instructable you sent did **[D]** |
| **Coil-on-Module (CoM)** | The module carries its own tiny coil. A separate **booster antenna** in the card body (a big perimeter loop plus a small coupler loop around the module) is inductively coupled to it. **There is no electrical connection.** | There are no antenna pads to solder to. You would have to design a new booster: a ring-sized loop plus a coupler coil precisely aligned with the module's coil. That is **[T]/[E]**, and much harder. ([booster antenna patents](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9646242), [US9070979](https://patents.google.com/patent/US9070979)) |

You cannot tell from the outside which type a card is. Many cards issued recently use CoM, because it
makes manufacturing cheaper. A cheap way to check without damaging the card: hold it in front of a bright
torch. A wire coil often shows as a faint shadow, and a coupler loop around the chip suggests CoM.
Confirm on a sacrificial card of the same issuer and batch before touching the live one.

## 2. What the published demonstration actually shows

The source is your PDF: *"RFID NFC Tap and Go Ring for Credit Card Payment"*, Instructables,
pockybum522, 21 Apr 2019. The relevant facts:

* Dissolved a duplicate card in acetone (about 1–1.5 h), recovered the module and its **30.0 in (762 mm)**
  wire antenna. **[D]**
  The module is "not strong at all"; bending it breaks traces, and the author lost cards this way.
* Filed the module's carrier narrower, without cutting the traces that run to the two outer antenna pads.
  **[D]**, but destructive if done wrong.
* Re-wound **15.0 in (381 mm)** of magnet wire round a resin ring frame (about 5–6 turns at
  finger size). This was *half* the original length. The full and quarter lengths "worked, but you had
  to press right up against the reader". **[E]**: tuning was found by trial and error, with no measurement.
* Final read range: "max range … about two inches", and in practice touching the terminal screen. **[E]**
* My own estimate supports the author's result: in
  [`antenna_results.md`](../electronics/calculations/antenna_results.md), a 6-turn coil at a 19–20 mm
  finger gives about 1.6–1.9 µH. That is a plausible resonance for a payment chip's input capacitance.
  The real capacitance of a payment chip is **not published**, so this is **[T]**.
* It was US (2019), on a bank that issued a second card **with the same number**. That is not normal UK
  behaviour (see §4).

Conclusion: transplanting a wire-bonded card **can** work for a skilled person, with short range and some
luck. Nothing in the source shows it works for CoM cards. Nothing shows long-term reliability.

## 3. Cheapest UK donor options (search snapshot, 2026-10-11, not purchased)

| Option | Physical card cost | Activation | Notes |
|---|---|---|---|
| **Monzo** (free current account) | Card free; **2 free replacements per year, then £5** ([Monzo fee information](https://monzo.com/legal/fee-information/version-1-11)) | App plus identity verification | Strong £0 donor candidate. You need to know whether a replacement cancels the previous card (it normally does). |
| **Starling** (free current account) | Card free; old sources say the first replacement is free, then £5 ([Which? 2020](https://www.which.co.uk/news/2020/09/monzo-and-starling-introduce-new-fees-are-you-willing-to-pay-for-your-current-account)) | App plus ID | **Unverified for 2026.** |
| **Curve** (card aggregator) | Old 2023 schedule: £5.99 delivery for a Standard physical card ([Curve fee PDF](https://cdn.buttercms.com/D6UBpsOhSBe0Ob9gGNig)) | App plus ID | Curve's current plan names have changed ([Curve help](https://help.curve.com/en_gb/fees-HkkKBu2Lu.md)). |
| Prepaid cards (Pockit, Suits Me, etc.) | Usually a card fee and/or monthly fee | ID verification required by UK anti-money-laundering rules | No cheaper than a free current account, and often have worse terms. |
| Cash App Card | **Not available.** Reports say Cash App stopped serving UK users on 15 Sep 2024 ([investingintheweb](https://investingintheweb.com/?p=15171)) | — | Excluded: the project must work in the UK. |

So the cheapest *donor* is effectively **£0–£5**: a free replacement card from a free UK current account.
The card price was never the real cost. The real costs are the risks below.

## 4. Why Approach A fails as a primary architecture

1. **One live physical card at a time.** UK issuers normally cancel the old card when the replacement is
   activated. Your ring would *be* the account's only physical card. **[U]** that two working cards
   would exist. Check with the issuer.
2. **Strong Customer Authentication (SCA).** Since 2021 UK issuers have typically forced chip-and-PIN after
   **£300 cumulative or 5 consecutive contactless payments**. From 19 Mar 2026 the FCA lets firms with strong
   fraud controls drop that rule, but **the £100 single-tap limit stays for now**
   ([Which?](https://www.which.co.uk/news/article/contactless-100-cap-ending-how-to-protect-yourself-from-fraud-aziUi3d0QZTq),
   [ITV](https://www.itv.com/news/2025-12-18/firms-could-set-own-contactless-card-limits-under-changes-planned-by-regulator)).
   A ring cannot be inserted into a chip reader. Whether a given issuer resets the counter through online
   PIN or app login, or has dropped it, is an **open question for each issuer**. If it can't be reset, the
   ring stops working every few days.
3. **The issuer owns the card.** UK cardholder terms normally say the card remains the issuer's property
   and must not be damaged or tampered with. Modifying it is not fraud (no credentials are copied), but it
   can be a breach of contract, and the issuer may block the card or close the account. **Ask for written
   permission first.**
4. **Destructive and unrecoverable.** Acetone attacks the PVC, and the module carrier cracks easily. A
   mistake means waiting for another card, and you get two free replacements a year at best.
5. **Expiry and reissue.** The ring dies at card expiry (typically 3–5 years) or on any fraud reissue. You
   would have to rebuild it each time.
6. **CoM cards** (see §1) may make it impossible without a booster-antenna design.
7. **Re-personalisation is impossible.** Once the module is out of the card, nobody can re-personalise it
   for you. This is correct and intended: the keys cannot and must not be extracted.

## 5. If you still want to try it (safe sequence)

1. Phase 2 first. Practise on £0.50 NTAG/MIFARE PVC cards: dissolve, recover the module, re-wind a coil
   with the `jig_coil_former` STL, and measure range (tests ANT-01…05).
2. Get the issuer's written OK, and confirm how a replacement affects the existing card.
3. Before cutting the live card, do the torch check, then confirm wire-bonded rather than CoM on a
   sacrificial card from the same issuer.
4. Test the recovered module with the original antenna *before* filing anything.
   Use a low-value purchase you are authorised to make.
5. Only then consider a re-wind. The ring design supports `payment_mode="none"` with a coil channel for
   this experiment.

**Never** try to read, copy, emulate or "clone" the card's data or keys. That is not a ring project, it is
fraud, and modern EMV cryptography is designed to make it useless anyway.

## 6. Answers to the brief's specific questions

| Question | Answer |
|---|---|
| Does removing the visible chip keep contactless working? | **No** on its own. The antenna is in the card body. You need the antenna, or a working replacement (§1). |
| Can a replacement antenna work? | Yes for wire-bonded modules **[D/E]**; it needs tuning by trial or measurement. For CoM it is only **[T]**. |
| Does bending the antenna matter? | Bending the *wire* is fine, because inductance depends on loop area and turns. Bending or cracking the *module carrier* destroys it. |
| Does the chip work after modification without re-personalisation? | Yes if it is undamaged; personalisation lives in the SE's memory. |
| Is activation by app or ID required? | Yes. For any UK account, KYC (identity) checks are a legal requirement. |
| What happens on block, replacement or reissue? | The ring stops working permanently. |
| Is periodic Chip & PIN a blocker? | Possibly. It depends on the issuer after the March 2026 FCA change. **Must be verified.** |

**Bottom line:** the cheapest donor costs about £0, but expect a range of 0–5 cm, contractual risk, a
life of 3–5 years, and possible SCA lock-outs. Approach D (below) gives a supported, activatable device
for roughly £25–£75.
