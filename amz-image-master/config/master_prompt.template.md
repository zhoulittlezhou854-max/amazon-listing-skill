# Master Prompt Template

Use this template to build the brand-and-shot prompt skeleton before sending a task to `image2`.

## 1. Brand Master Block

Brand: `Tosbarrft`
Platform: `Amazon`

Core brand direction:

- professional and reliable outdoor recording brand
- youthful but credible
- cool, clean, and conversion-focused
- above cheap generic devices, below premium flagship intimidation

Visual system:

- preserve real product structure, materials, and proportions
- keep layouts clean and Amazon-friendly
- use outdoor-tech energy without poster-style chaos
- maintain black/white foundations with controlled blue or orange accents when helpful

## 2. Product Consistency Block

Replace fields with the real product facts:

```text
Product: [product_name]
Category: [category]
The product appearance, color, structure, proportions, and key parts must remain consistent with the provided reference images.
Do not invent components, buttons, ports, accessories, or product functions.
```

## 3. Shot Task Block

Replace fields with the real task:

```text
Current asset: [shot_id] / [shot_type]
Objective: [objective]
Layout rule: [layout_rule]
Copy slots: [copy_slots]
Must include: [must_include]
Must avoid: [must_avoid]
Use the provided references from [reference_binding].
```

## 4. Output and Restriction Block

```text
Create an Amazon-style ecommerce image that feels clear, commercially strong, and consistent with the Tosbarrft visual system.
Keep the product as the hero.
Maintain crisp lighting, readable hierarchy, and controlled information density.
Avoid poster-like overdesign, clutter, and cheap generic gadget styling.
```

## 5. Main Image Variant

Use this override for `IMG01`:

```text
Create a clean Amazon main image on a white background.
Show only the product and allowed included accessories if required by the listing strategy.
Do not add copy, icons, callouts, badges, logos, or lifestyle scenery.
Keep the product dominant, accurate, and trustworthy.
```

## 6. Hero Selling Point Variant

Use this override for `IMG02`:

```text
Create a hero Amazon feature image that establishes the visual language for the rest of the set.
Use one core message, a strong product focal point, and 2-4 proof-driven support elements.
Make it feel energetic and outdoor-capable, but still clean and commercially readable.
```

## 7. A+ Variant

Use this override for A+ modules:

```text
Create an A+ style module for Amazon that extends the Tosbarrft brand system.
Allow more atmosphere and storytelling than listing detail images, but keep the layout commercially clear and product-led.
Avoid drifting into abstract campaign art.
```
