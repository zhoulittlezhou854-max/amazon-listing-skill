# Historical Structure Analysis — H91POR_US (Training Sample)

## 1. Input Signals Recap
- **ABA keywords**: Same 50-term deck as lite model but interpreted for “Pro” kit — top-tier volume on `pov camera`/`motorcycle camera`/`mini body camera`; mid-tier adds `clip cam`, `thumb action camera`, `travel camera`; provides CTR + impression columns for intent tiering.
- **Competitor order-winning sheet**: Shows conversion spike for niche keywords (`body camera`, `bodycam`, `travel camera`), plus 需供比 extremes (e.g., `pov camera` 26.7) indicating low-competition scenes. Combined with `购买率` gives clear High-Conv candidate list for Title/B1/B2.
- **Attribute table + supplement**: Base specs mirror lite SKU (1080p, no EIS) but supplemental file upgrades capability constraints: waterproof case enabling IP68/30 m, battery split (700 mAh internal + 1600 mAh pod) for total 360 min, expanded accessory stack (battery pod, waterproof housing, helmet/bike mounts). Hard boundaries remain: no stabilization, base unit not waterproof without case.
- **Review/multi-dimension CSV**: Same pain buckets as lite (accessory mismatch, overheating, app instability) but competitor bullets highlight “thumb sized” + “360 min runtime + external pod”. Some competitor listings promise remote app control + waterproof claims.

## 2. Historical Listing Structure (Docx Audit)
- **Title formula**: `[Brand] + [Runtime] + [Lens/Mount capability] + [Use case] + (Spec bundle)`. Runtime emphasises “6-Hour” + 180° lens + magnetic clip; use-case string is “Daily Vlogging and Hands-Free Content Creation”; spec bundle includes resolution, storage (128GB), form factor cues. IP68 housing mention moves to bullets/description, keeping visible claim compliant (“with waterproof case”).
- **Bullet role allocation**:
  - **B1**: Magnetic clip mounting + scenario coverage (vlog, cycling, commuting). Similar to lite but highlights helmet/backpack attachments.
  - **B2**: Numeric runtime, but now splits internal (150 min) + external pod (210 min) for 360-min total, explicitly suited for long shifts/evidence.
  - **B3**: Focuses on 180° rotatable lens + 1080P + persona set (security, delivery riders, office). Mixes capability + audience bridging.
  - **B4**: Waterproof case claim: states IP68 + 30 m depth + specific use cases (snorkeling, rainy rides) with boundary “with included housing”.
  - **B5**: Weight (44.8 g), touchscreen, WiFi/app control—drives usability & shareability to creative persona.
  Format same as lite (EM DASH, <200 chars), but B4 now statutory boundary slot.
- **Description**: Headline reuses runtime + lens. Intro covers POV creator persona but adds caution (“waterproof up to 30 m only when using the included waterproof case”). `[Technical Specifications]` enumerates waterproof level with conditional clause and restates “No EIS”.
- **Alt text**: 7 entries map capability to scenario + persona (delivery rider, snorkeler, YouTuber), showing scene diversification beyond urban commute.

## 3. Keyword & Search-Term Behavior
- **Search Terms**: Same string as lite plus backend-only long-tail (“4k action camera”, “stabilization camera”) even though spec doesn’t support them—a hint that backend-only tagging is expected for banned claims once capability fuse is enforced.
- **STAG plan**: Four clusters: Professional Body Cam (security/delivery), POV creator, Mini & Discreet (students/journalists), Wearable Lifestyle (travel/sports). Each includes constraint/response mapping referencing runtime, magnetic clip, 30 m waterproof case.

## 4. Capability · Scene · Audience Distribution
- **Capability-scene binding**: Scenes expand to underwater/sports thanks to accessory kit; B4 explicitly ties IP68 + case to snorkeling/outdoor rides; B2/B3 maintain commute/evidence coverage; B5 fosters creative/social sharing. Primary scene order inferred: commuting/security → POV creators → underwater sports → wearable lifestyle.
- **Numeric evidence**: Runtime split 150+210=360 (B2), 30 m depth (B4), weight 44.8 g (B5). Title uses runtime but leaves numeric depth for bullet, aligning with Rule 3b boundary requirement.
- **Audience**: Delivery riders, security staff, TikTok/YouTube creators, students/journalists, travelers/sports enthusiasts all appear via bullets/alt/STAG.

## 5. Data Routing Observations
- L1 keywords feed Title/Alt text (body camera/action camera). L2 (magnetic clip, clip cam) land in B1/B5. L3/residual (camara para grabar contenido, aura pov cam) only in Search Terms.
- Supplement text drives runtime + accessory claims; attribute truth ensures “with included waterproof case” qualifiers. Absence of stabilization ensures no visible EIS claim; backend ST retains “stabilization camera” requiring backend_only flag.
- Review pain points steer boundary phrases (“only when using included waterproof case”) to pre-empt accessory mismatch complaints.

**Takeaways**: Pro SKU follows same macro structure but B4 becomes compliance-critical boundary statement slot for capability upgrades; search terms may include backend-only risky keywords that must be tagged; runtime messaging splits internal vs external pods; persona coverage broadens with underwater scenes enabled only via accessory disclaimers.
