# Historical Structure Analysis — H91lite_US (Training Sample)

## 1. Input Signals Recap
- **ABA keywords**: 50 English terms with clear tier separation — L1 volume cluster (>20k) focuses on “POV/motorcycle/mini body camera” intents; L2 captures wearable/clip/thumb variants; L3 includes Spanish phrases for “camara para grabar contenido” style long-tail. Columns include search volume, rank, impressions, clicks, enabling CTR-derived intent grouping.
- **Competitor order-winning sheet**: 26 rows mixing keyword + per-ASIN win rates; despite missing explicit price column, monthly purchase + conversion rate columns highlight “body camera” > “wearable camera” as conversion-heavy while niche mounts (clip cam, thumb cam) show low competition (high 需供比).
- **Attribute table**: Truth layer confirms 1080p sensor, 1.47" screen, 700mAh internal battery (~150 min), fixed focus, WiFi 2.4GHz, Type-C, non-waterproof, accessories limited to body + USB cable. “Has Image Stabilization: No” and “Water Resistance Level: Not Water Resistant” set strict capability fuse boundaries.
- **Supplemental TXT**: Adds kit context (magnetic/neck strap/back clip/32GB card) and cautions (“no stabilization; not for high vibration; clip doesn’t rotate, lens does”).
- **Multi-dimension CSV**: Competitive listings emphasize lightweight clip-on POV capture and highlight battery duration + accessory completeness. Review insights tag three dominant pain buckets: missing accessories vs images, device overheating/lockups, and unstable app connections/battery shortfalls.

## 2. Historical Listing Structure (Docx Audit)
- **Title formula**: `[Brand] + [Battery runtime] + [Mount/Optic capability] + [Primary audience] + (Spec pack)]`. Runtime (6-hour) plus 180° lens & magnetic clip lead, followed by use cases (“daily vlogging”, “hands-free content creation”) and spec pack (resolution, storage, form factor). L1 keywords (“action camera”, “body cam”) appear once each; tone stays factual, no promo words.
- **Bullet role allocation**:
  - **B1** foregrounds mounting flexibility + POV scenes (daily vlog/urban travel). Capability mix = mounting + scenario.
  - **B2** is the numeric proof slot: 150-min runtime + 700mAh battery, explicitly tying to commute/session length.
  - **B3** addresses evidence/security persona, binding resolution + compliance use case (“record interactions”).
  - **B4** focuses on control UX (touch screen) rather than raw specs, showing strategic swap-in when stabilization is unavailable.
  - **B5** handles ergonomic proof (weight <50g) to serve comfort/audience dimension.
  Each bullet uses EM DASH, <200 chars, scenario and numeric data well placed.
- **Description pattern**: Headline anchors unique hardware (rotating lens). Intro merges creator + professional personas, clarifies best-use context (“walking/stationary” because no EIS). `[Technical Specifications]` mirrors attribute truths including explicit “Not Water Resistant” and “Fixed Focus (No EIS)`. Accessories mention limited kit only in packaging sentence.
- **Alt text**: Seven lines, each `[Brand capability] for [scenario] - [audience]`, reusing hero lens capability plus persona labels (content creator, security staff, traveler). Provides persona coverage for COSMO.

## 3. Keyword & Search-Term Behavior
- **Search Terms**: Blend of generic “body cameras with audio and video recording”, format variants (“clip cam”, “mini action camera”, Spanish long-tail). Residual keywords avoid duplication of Title/Bullets, leaning on plural/residual forms and mix of English + localized Spanish to capture long-tail conversions.
- **STAG mapping**: Module 6 table groups into Security, POV Creative, Ultra-Portable scenes. Each includes High-Conv terms plus constraint/response lines referencing battery or mount, showing how High-Conv keywords inform ad angle selection.

## 4. Capability · Scene · Audience Distribution
- **Capability-scene bindings**: With no stabilization/waterproof, copy leans on rotation + mounting for creative scenes, while statistical bullet (B2) covers battery (P1). Security/evidence persona uses B3 to tie to reliability; creative/daily vlogging persona spans Title, B1, B5, Alt Text. Scene priority effectively: daily vlog/urban travel → security/evidence → commuting/POV lifestyle.
- **Numeric evidence**: Battery minutes + battery capacity in B2, weight (44.8g) in B5, resolution repeated in Title/B3, accessory mention limited to packaging and STAG responses. Technical specs table reaffirms every numeric claim, preventing Rufus conflicts.
- **Audience & persona**: Title/Alt text mention “daily vlogging”, “hands-free content creation”, “security staff”, “service staff”. Bullets reference commutes, security interactions, and creative sessions, aligning with COSMO personas.

## 5. Data Routing Observations
- High-volume ABA terms (POV camera, body camera) fed Title + STAG; mid-tier (magnetic clip, clip-on camera) appear in bullets/Alt text; long-tail bilingual terms parked in Search Terms.
- Order-winning sheet’s conversion-focused “body camera” / “wearable camera” keywords correlate with B3 persona emphasis and STAG “Professional Security” cluster.
- Attribute truths limit claims: no waterproof/EIS references anywhere, and runtime claims rely on supplemental text (700mAh/150 min). Manual supplement lines (“not for high vibration”) indirectly reflected where description says “walking or stationary use”.
- Review pain points (missing accessories, overheating, app instability) indirectly inform boundary statements: listing avoids promising waterproof or extra kit, focuses on basic included clip + card to prevent mismatch.

**Takeaways for rule induction**: For low-spec/lite body cams, Title leans on runtime + mount rather than resolution; B2 must quantify battery; B3 reserved for evidence persona; B4 can showcase control interface when stabilization absent; Search Terms should mix English/Spanish residuals while keeping risky claims backend-only. Boundary statements about use context belong in description rather than bullets to keep B4 flexible when spec set lacks constraints beyond “walking/stationary”.
