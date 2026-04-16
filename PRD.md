# Architecture Roadmap: v9.0 (Traffic & Conversion Engine)

This document outlines the next phase of the Amazon Listing Pipeline. The focus shifts from "producing clean local copy" to "maximizing A10 indexation, COSMO conversion, and data-driven feedback loops."

## 1. Algorithmic Visibility (A10 Hard-Routing)
**Goal:** Expose keyword routing gaps to the operator to maximize indexation.
- **Action:** Enforce strict slotting (L1 -> Title, L2 -> Bullets 1-3, L3 -> Search Terms).
- **Reporting:** In `report_generator.py`, output an explicit delta matrix: "Required vs. Actual". E.g., `[Title Slot: Missing 1x L1 keyword]`, `[Backend-only: 3 high-volume keywords quarantined]`. This tells PPC/SEO operators exactly what to supplement.

## 2. COSMO Micro-Narratives (Persona-Driven Briefs)
**Goal:** Move from static scene templates to dynamic, persona-driven storytelling.
- **Action:** In `intent_translator.py`, generate dynamic "Mini-Briefs" for each `IntentNode` (e.g., "Food Delivery Rider in Rain" or "Family Ski Trip").
- **LLM Integration:** Pass this Mini-Brief + Canonical Accessories into the LLM payload. Instruct the LLM to weave the features into this specific micro-story to maximize COSMO relevance scores.

## 3. Accessory -> Experience Pipeline (The 3-Step Structure)
**Goal:** Prevent the LLM from simply listing accessories. Force experiential writing.
- **Action:** In `preprocess.py`, map every canonical accessory to a `[Posture + Pain Point]`. (e.g., `magnetic back clip -> true hands-free POV recording without chest straps`).
- **Prompting:** Update the Bullet prompt to strictly enforce a 3-step structure: `[Scene] + [Action/Posture using Accessory] + [Feeling/Resolved Pain]`.

## 4. Rufus & Multimodal Synergy
**Goal:** Create a feedback loop between visual assets and text intents.
- **Action:** Extract the `[Visual Design Brief]` generated in A+ content.
- **Expansion:** Send these Canonical Specs + Design Briefs to a Multimodal engine (or image generation API) to create matching A+ image cards.
- **Graph Write-back:** Store the resulting image URLs/IDs back into the `intent_graph` for future multimodal COSMO retraining.

## 5. AI Control Plane (Compute Tiering)
**Goal:** Allocate LLM compute based on listing value/traffic, and document the generation state.
- **Action:** Split generation into 3 explicit tiers:
  1. `Native LLM` (GPT-4o/Claude 3.5 - High compute, fluid)
  2. `LLM Polish` (Smaller local model - Medium compute)
  3. `Rule-Based Fallback` (Deterministic, zero compute)
- **Reporting:** Tag every generated field in the report with its compute tier (e.g., `[Bullet 1: Native]`, `[Title: Fallback]`). Allow operators to force `Native` reruns for high-ROI ASINs.

## 6. The Data Closed-Loop (ROI Write-back)
**Goal:** Let real-world ad performance dictate the Intent Graph.
- **Action:** Add an ingestion endpoint for Amazon Search Term / PPC reports.
- **Analysis:** Automatically cross-reference high-converting search terms against the `canonical_specs` and `intent_graph`.
- **Feedback:** If "magnetic clip" drives the highest CTR, the system automatically boosts its priority weight in `writing_policy.py` for future generations.
