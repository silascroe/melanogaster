# Male Drosophila macro study

This is a new Blender 5.2.2 model, built independently of the older `realistic_fly/` and `realistic_fly_hero/` files. `male_drosophila_macro.blend` is editable; `build_fly.py` regenerates its meshes, shaders, lights, camera, and render.

The model includes close-packed compound-eye facets and microbristles, antennae and branched aristae, textured thoracic plates and tapered bristles, a banded male abdomen, six jointed legs with a small male foreleg sex comb, halteres, and translucent wings with radial, medial, and cubital vein paths. It is a procedural anatomical **art study**, not a specimen scan or a validated biological reconstruction. The studio render is deliberately detailed; its geometry is not yet optimized for Godot.

## Render

From the FlyTest root in PowerShell:

```powershell
& 'tools\blender\blender-5.2.2-windows-x64\blender.exe' -b -t 8 --python 'artwork\blender\realistic_fly_from_scratch\build_fly.py'
```

The script saves the `.blend` before rendering, then writes a 2400×1800 portrait to `outputs/blender/realistic-fly-from-scratch/male_drosophila_macro.png` and a 2000×1500 close-up to `male_drosophila_detail.png`. It uses the local GTX 1070 through Cycles CUDA when available and falls back to CPU. For faster 1200×900 previews, set `FLY_RENDER_PREVIEW=1` before running; it writes `male_drosophila_preview.png` and `male_drosophila_detail_preview.png`. Render outputs are ignored by Git, but remain on disk locally.

The first-pass `.blend` and render are preserved with `_first_pass` names for visual comparison. The current script and `male_drosophila_macro.blend` are the refined version.

## Authored texture pass

`male_drosophila_textured.blend` is a separate, editable texture study built on
the refined model. It has eleven 1024-pixel PNG maps under `textures/`: cuticle
color, microheight, and roughness for the thorax, head, and abdomen; regional
compound-eye pigment; and a tinted, variable-opacity wing membrane. The maps
are also packed into the `.blend` so it can be opened on its own. The existing
facet, bristle, and vein geometry remains geometry.

`author_textures.py` deliberately paints layered, reproducible masks in Blender:
cuticle flecks and setal sockets, dorsal thorax pigmentation, darker face
margins, abdomen edge darkening, regional eye pigment, and a warm wing costa.
These are original, reference-guided illustrations. They are not sampled from
or traced over any photograph, and they are not claims of specimen-level
accuracy. The baseline `.blend` is preserved for comparison.

To rebuild from the FlyTest root:

```powershell
& 'tools\blender\blender-5.2.2-windows-x64\blender.exe' -b 'artwork\blender\realistic_fly_from_scratch\male_drosophila_macro.blend' -t 8 --python 'artwork\blender\realistic_fly_from_scratch\author_textures.py'
```

The textured renders are `outputs/blender/realistic-fly-from-scratch/male_drosophila_textured_macro.png`
and `male_drosophila_textured_detail.png`. This is a Blender look-development
asset. It has not been optimized or exported for Godot; the Blender shaders
would need to be adapted for that renderer.

Reference for general adult morphology: [Drosophila Stock Center Mexico adult anatomy](https://bancodemoscas.fciencias.unam.mx/Morfologia%20Adulto.html) and [Drosophila Photography, *D. melanogaster*](https://drosophoto.com/drosophila-melanogaster/). The eye facet scale was informed by a [Drosophila eye review](https://pmc.ncbi.nlm.nih.gov/articles/PMC2890271/); the small male foreleg comb by a [foreleg anatomy study](https://pmc.ncbi.nlm.nih.gov/articles/PMC10335707/). No reference photograph was used as a texture or copied into this folder.

For the texture pass, I also consulted the [wild-type anatomy atlas](https://academic.oup.com/genetics/article/228/2/iyae129/7750380) and [abdominal pigmentation study](https://pmc.ncbi.nlm.nih.gov/articles/PMC5608185/) for the distinction between cuticle, bristles, wing membrane, and male abdominal pigmentation. Exact color varies with specimen, lighting, and age; the maps are an art interpretation.
