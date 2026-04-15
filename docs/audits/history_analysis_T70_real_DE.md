# Historical Structure Analysis — T70_real_DE (Training Sample)

## 1. Input Signals Recap
- **ABA sheet (DE)**: German-language keywords with EU metrics: top L1 include “action cam”, “action cam 4k”, “mini action cam”, “dashcam fahrrad”, “helmkamera”, with search volume + rank history + PPC bids + click/convert concentration; indicates multi-scene demand (security, cycling, underwater, vlog) in German synonyms (körperkamera, vlog kamera, motorrad kamera).
- **Order-winning sheet**: 22 rows with conversion-heavy long-tail (e.g., “dashcam fahrrad” 2.27% CVR, “bodycam körperkamera mini” 1.25%, “mini action cam” 1.03%). Provides quantifiable High-Conv sample tied to localized nouns, underlining that L2/L3 scenes must be localized (German language) and that cycling/safety scenes convert best.
- **Attribute table**: Higher-spec hardware: 4K capture, dual screen, EIS (“Has Image Stabilization: Yes”), waterproof (with housing). Weight 66 g, 64MP stills. Truth set allows visible 4K/EIS claims but requires houses for waterproof (per supplement: 30 m with case; 5K mode lacks stabilization). Connectivity includes Wi-Fi for app control. Hard boundaries: only 1080P/4K support EIS; 5K unsupported; waterproof only with included housing.
- **Supplement**: Reiterates dual screen + EIS + Wi-Fi; states 30 m waterproof with case; warns 5K lacks stabilization, so claims must degrade; indicates magnetic accessories for neck/metal surfaces + additional mounts (bike/helmet).
- **Multi-dimension CSV**: Listing_content + Review_Insight lines emphasize magnet attachments, dual displays, 30 m waterproof, 64MP photos. Pain points highlight necklace discomfort, image quality vs GoPro, touch-screen complexity, stabilization/night vision complaints—driving boundary statements.

## 2. Historical Listing Structure (Docx Audit)
- **Title (German)**: “TOSBARRFT Bodycam Körperkamera zur Beweissicherung & Sicherheit, 4K Ultra HD Action Cam mit magnetischer Halterung, 66g Leichtgewicht, Dual-Display, WiFi App-Steuerung, 64MP Foto”. Structure: `[Brand + dual identity (Bodycam + Action Cam) + key capability (4K, magnetic mount) + weight + dual display + WiFi + spec (64MP)]`. Title front loads German nouns for legal/evidence use (“Beweissicherung & Sicherheit”), aligning with High-Conv keywords.
- **Bullets** (German) follow strict roles:
  - **B1**: Magnetisches montagesystem + Sicherheits use case (bodycam). Scenes: safety/legal, persona: everyday security. Capability: magnet mount + 4K + 66 g.
  - **B2**: Cycling-specific bullet referencing EIS (stated as 1080P EIS) for bike dashcam/helmet use; shows numeric tie to scenario (shock absorption). Combines capability (EIS) + scene (cycling) + persona (radfahrer) — bridging used_for_func + used_for_eve.
  - **B3**: Dual display + vlogging persona, solving selfie control; addresses creative/travel persona.
  - **B4**: Waterproof + 30 m depth (explicit) + scenario (underwater/outdoor). Serves boundary requirement (“mit Gehäuse”). Includes 64 MP still spec.
  - **B5**: App control + accessories list + warranty (24 months). Emphasizes completeness + trust (after-sales). Each bullet short (<200 chars), uppercase header analog achieved by sentence case but bullet style replicates required structure.
- **Description**: Two-paragraph narrative emphasises safety/evidence and cycling/dashcam use. Mentions EIS best at 1080P and need for waterproof case. `[Technical Specifications]` restates 4K capture, dual display, 64MP photo, WiFi, waterproof (with case). FAQ section clarifies waterproof case requirement, EIS mode limitations, mounting kit contents, WiFi streaming, weight + warranty.
- **Search Terms**: German long-tail list mixing nouns (`dashcam fahrrad`, `helmkamera skifahren`, `körperkamera`, `bodycam kaufen`, `kamera vlog`, `action cam zubehör`). Balanced mix of L1-L3 localized terms; includes “4k” to maintain coverage; duplicates Title terms but acceptable in backend for German synonyms.

## 3. Keyword & Routing Observations
- Title covers dual L1 keywords (bodycam, action cam). B1/B2/B3/B4 embed German intents (körperkamera, dashcam fahrrad, dual-display for vlog). Search Terms include majority of long-tail from ABA/order-winning lists. ST includes biking, skiing, motorrad, zubehör to capture accessories.
- STAG/ad strategy highlight high-level clusters: safety (bodycam/körperkamera), cycling (dashcam fahrrad/helmkamera), vlog creation (vlog kamera/action cam 4k), mini/discreet (mini action cam). Each cluster ties pain point to response (shock absorption, magnet mount, waterproof kit).

## 4. Capability · Scene · Audience Coverage
- Scenes: security/evidence, cycling/commuting, vlogging/content creation, underwater/outdoor adventure. Title + B1 emphasize security; B2 cycling; B3 vlogging; B4 underwater; B5 after-sales/support. Audience includes safety personnel, cyclists, Vloggers, travelers, snorkelers.
- Capabilities: 4K/EIS (visible due to specs), dual display, waterproof (with case), magnetic mount, 64MP, WiFi app control. Numeric specifics: 30 m depth, 66 g weight, 64MP, 24-month warranty. Boundaries (EIS not in 5K, waterproof requires housing) appear in FAQ/description.
- Evidence: Modules emphasise “Beweissicherung” (legal evidence) — Title uses law & safety cues, aligning with Germany’s privacy/security expectations.

## 5. Compliance/Boundary Handling
- Title avoids banned claims; B4 and FAQ mention waterproof only with case. FAQ explicitly states EIS limited to 1080P/4K, not 5K, fulfilling ActionCam fuse requirement. Bullets avoid competitor comparisons despite review references to GoPro.
- No promotional language; emphasises warranty/after-sales responsibly.

**Takeaways for rule induction**: For higher-spec DE SKU, Title must mix German bodycam + action cam nouns plus dual capabilities; B2 slot dedicated to numeric EIS/cycling; B4 ensures waterproof depth + boundary; Search Terms pivot to localized nouns; boundary statements (waterproof housing, EIS mode limits) belong in both bullets and FAQ to appease ActionCam compliance. German copy requires formal tone and persona-specific nouns. Numeric evidence (depth, weight, 64MP) distributed across B2/B4/B5; after-sales mention anchors trust (24 Monate). Scenes & capabilities map strongly to A10/COSMO scoring expectations.
