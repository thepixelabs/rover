# Prompts — pack-a-relay-noir

---

## Round 2026-04-23 — b2 mascot hero regeneration

### MCP call parameters

```
tool: mcp__mcp-imagen__imagen_t2i
model: imagen-4.0-ultra-generate-001
aspect_ratio: 4:3
num_images: 1
output_directory: /home/user/Documents/git/dispatch/src/assets/rover/packs/pack-a-relay-noir
```

Post-processing:
- Raw file saved as: `b2-mascot-hero.v2.raw.png`
- Chroma-key: `magick b2-mascot-hero.v2.raw.png -fuzz 8% -transparent "#E12F8F" b2-mascot-hero.v2.png`
  - Note: sampled actual background color was #E12F8F (not pure #FF00FF — Imagen rendered hot pink)
  - Fuzz 8% chosen after testing 6%, 8%, 10%; all preserved character body cleanly
- Final transparent PNG: `b2-mascot-hero.v2.png` (also overwrites `b2-mascot-hero.png`)

---

### b2-mascot-hero.v2.raw.png

```
Graphic novel illustration, comic book ink style, flat cel shading, thick confident black ink outlines. SOLID MAGENTA #FF00FF background edge-to-edge, no gradients, no shadows on background.

Character: A stocky hooded courier in a heavy utility long coat, the character's head is a large satellite dish — the dish has a thick glowing CYAN/TEAL neon rim-light band, very bright. The face/head area beneath the dish is a dark silhouette with no visible eyes or mouth, only a faint cyan ambient glow. The coat has tactical pockets and gear. One arm extends toward a stack of devices. A glowing coiled cyan cable runs from a port on the character's chest/satchel and splits into three, connecting to all three devices. Character stands on the RIGHT side of the frame in three-quarter pose.

THREE DEVICES stacked loosely on the LEFT side, each screen glowing bright cyan:
1. TOP — a boxy CRT terminal / retro server rack unit: square cathode-ray screen, blinking indicator LEDs, cables plugging into the back. Represents a background runtime process.
2. MIDDLE — a laptop/desktop monitor showing a dashboard with tiled panel grid, cyan glow from the screen illuminating the desk surface.
3. BOTTOM — a small handheld pocket terminal / phone with a glowing cyan keypad and terminal readout lines on screen.

The single glowing coiled cable from the mascot visually connects to all three devices — clearly depicting ONE stack, three surfaces.

Style requirements: Mignola / Becky Cloonan graphic novel aesthetic with cyberpunk neon accents. Heavy black linework. Flat comic-book cel shading, NOT painterly, NOT photoreal, NOT 3D render. Color palette: very dark navy/charcoal body, CYAN/TEAL neon only for all glows and accents — dish rim, cable, all three screens, hand glow. No purples, no reds, no oranges, no warm colors. Dramatic chiaroscuro: dark body with bright cyan edge-light on the dish rim and screen-glow bouncing back onto the figure. The cyan rim of the satellite dish is the brightest element in the image. No text, no logos, no words inside the image.
```

---

### b2-mascot-hero.v2.png / b2-mascot-hero.png

Transparent final — result of chroma-keying `b2-mascot-hero.v2.raw.png` as described above.
Dimensions: 1280x896, TrueColorAlpha.
