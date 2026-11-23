# 14 — The photographic assets

The platform carries a small number of photographs. They are committed as
files, so the record of how they were made is kept here: a photograph that
cannot be traced back to its prompt cannot be re-shot in the same light.

## Where they live

| Asset | Path | Used by |
| --- | --- | --- |
| Kitchen hero | `static/img/kitchen-hero.jpg` | The sign-in and register screens, behind the access pass |
| Landing images | `static/img/landing/` | The public landing page at `/` |

## The kitchen hero

The photograph behind the access pass is a canteen in daylight: a serving
counter in warm daylight, a matte black dome lamp above it, pans of food on
the line, a stack of plates at the left, and nothing else — no people, no
text, no signage. It is the one daylight surface in a product that is
otherwise held in the Dusk palette, so it is shot to be warm and open rather
than dark and clinical.

It was generated at 2K, 16:9, JPEG, and committed at the size it is served
from. The prompt that produced it is kept here so the frame can be shot
again if it ever has to be:

```json
{
  "requests": [
    {
      "prompt": "Photorealistic wide interior photograph of a bright modern institutional cafeteria serving line, shot slightly from the left at counter height. Background: warm off-white plaster wall with soft daylight from a large window off-frame left, a tall leafy green potted plant with broad leaves at the far left edge, a matte black dome pendant lamp hanging from the top center with a warm glowing bulb. Foreground: a warm honey-toned wooden serving counter; at the bottom-left a neat stack of cream ceramic plates; running along the counter, stainless steel gastronorm pans and chafing dishes filled with steamed white rice, orange vegetable curry and green peas, with polished metal serving spoons resting in the pans and soft wisps of steam rising. Shallow depth of field, soft diffused natural light, airy and calm, muted warm cream and orange palette with cool stainless steel accents, clean minimal editorial composition, high detail, realistic materials. No people, no text, no lettering, no logos, no signage, no watermark, no dark or heavy shadows.",
      "aspect_ratio": "16:9",
      "area": "2K",
      "n": 1,
      "output_format": "jpeg",
      "output_file": "messforecast-kitchen-hero"
    }
  ]
}
```

The file is served as `static/img/kitchen-hero.jpg` and is drawn as a cover
background, so the crop is set in the stylesheet rather than in the file:
the subject sits on the right of the frame, where the ticket stands, and the
lamp hangs above the headline.
