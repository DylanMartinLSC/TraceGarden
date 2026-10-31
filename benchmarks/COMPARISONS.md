# Actual comparison coverage

The commercial comparison is limited to **12 public Vectorizer.AI example pairs**. We have **not benchmarked Vector Magic Desktop**, commercial service latency, commercial CPU usage or commercial memory use. TraceGarden timing/memory figures elsewhere in this folder measure TraceGarden alone. These results do not establish general commercial quality parity.

Each row below includes the original input and the vendor-provided SVG reference. Both SVGs are rendered at the input dimensions using resvg. Sizes are uncompressed SVG bytes. MAE is premultiplied RGBA error against the original input on a 0–1 scale. Lower input MAE can reward retaining JPEG noise or blur; it is not a perceptual quality ranking. The source set was selected by the vendor, not sampled independently.

| Example / original | Vectorizer.AI reference | Vectorizer.AI SVG bytes | TraceGarden SVG bytes | Vectorizer.AI input MAE | TraceGarden input MAE |
|---|---|---:|---:|---:|---:|
| [bubble-tea](https://vectorizer.ai/cf/vai/animations2/bubble-tea_f41266cea1ea537074a27b71c21cafbc.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/bubble-tea_9e8da9362815e313a3c6171cd875e97f.svg) | 49,609 | 141,331 | 0.020646 | 0.027146 |
| [bull-mascot](https://vectorizer.ai/cf/vai/animations2/bull-mascot_59e0d5c9270f6a776a1324dae79b75d5.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/bull-mascot_3646dacf2d438c970567b60e0344a2ee.svg) | 33,800 | 25,264 | 0.006746 | 0.009160 |
| [cloud-computing](https://vectorizer.ai/cf/vai/animations2/cloud-computing_86bdc57687a0bdfb6aa7b8980706a032.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/cloud-computing_0eb699a0b3a517dbed1b311f42bc2ec9.svg) | 85,549 | 67,224 | 0.007480 | 0.015625 |
| [coffee-fox](https://vectorizer.ai/cf/vai/animations2/coffee-fox_eaf3712a2ba066d5209f78b5407d7177.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/coffee-fox_8799ba71da1e3243591d15f68c26bf20.svg) | 50,660 | 33,354 | 0.008876 | 0.010921 |
| [coffee-shop](https://vectorizer.ai/cf/vai/animations2/coffee-shop_f6fa26dbf2c6a2fede8c8df9e0b962f4.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/coffee-shop_45467bb462dc932d08637a02e484781d.svg) | 54,280 | 37,374 | 0.010994 | 0.014427 |
| [geometric-shapes](https://vectorizer.ai/cf/vai/animations2/geometric-shapes_581e5f63d7b2728e9611ace7471ff3ac.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/geometric-shapes_a64df84d5011cb439cc4df46bf8d5ade.svg) | 8,225 | 12,597 | 0.004962 | 0.004688 |
| [leaping-stag](https://vectorizer.ai/cf/vai/animations2/leaping-stag_a9ef47f7033aa2db68514921da28a401.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/leaping-stag_ec6c14a23eb43fdfc44652fe450596a3.svg) | 110,293 | 110,364 | 0.007212 | 0.008906 |
| [lion-mascot](https://vectorizer.ai/cf/vai/animations2/lion-mascot_16e232c39c4b1e7e3f34fcd5683f41c8.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/lion-mascot_235d0b44bcbd4df0c3d022726576456f.svg) | 42,154 | 26,017 | 0.008728 | 0.015909 |
| [mountain-supply](https://vectorizer.ai/cf/vai/animations2/mountain-supply_8a2f8b3f470d16e41143917a3e475a9e.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/mountain-supply_f4e2d9efa7dc34fe1ba1a3b968fa1245.svg) | 51,169 | 38,145 | 0.018592 | 0.023033 |
| [national-park](https://vectorizer.ai/cf/vai/animations2/national-park_09e9162ac7b1aa413d2774df2ffe0241.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/national-park_12fff26cb1809c6b1bb42a48c53a26fd.svg) | 64,956 | 37,288 | 0.011462 | 0.015504 |
| [seaside-panther](https://vectorizer.ai/cf/vai/animations2/seaside-panther_47de219b64f8fd2efb738b5b5167eea3.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/seaside-panther_a88537f9ff1043f65455246bc211136d.svg) | 135,692 | 350,940 | 0.018680 | 0.023308 |
| [wolf-mascot](https://vectorizer.ai/cf/vai/animations2/wolf-mascot_1bbe657adc4da674ebeb2c794e8e3e0f.jpg) | [View SVG](https://vectorizer.ai/cf/vai/animations2/wolf-mascot_eb4ff7f59502007820d0b93763f0ba9e.svg) | 139,587 | 116,082 | 0.014399 | 0.022783 |

On these 12 examples, TraceGarden produces smaller SVGs on 8 and lower input MAE on 1. Neither statistic establishes better visual quality.

## Visual comparison

Generate an offline gallery with original raster, Vectorizer.AI reference, and TraceGarden output shown together. It includes synchronized zoom/scroll and paired metrics. Raw source/reference files remain in the local cache. Attributed comparison charts are also available in [the README](../README.md#visual-comparisons).

```sh
python benchmarks/reference_compare.py --download-public-examples
python benchmarks/comparison_report.py
# Open work/reference-comparison.html in a browser.
```

The gallery uses browser SVG rendering; numeric metrics use resvg. Raw results, source URLs, input/reference SHA-256 hashes, settings and environment details are in [reference-results.json](reference-results.json). The [main report](README.md) also lists error between the two outputs and measured TraceGarden resource use.
