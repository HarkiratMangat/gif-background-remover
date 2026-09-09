# `detect_bg_color` audit over the DEVOID logo corpus

*Measured 2026-09-09 10:21 EDT. 101 readable images under `/Applications/Claude Code/Devoid/DEVOID Logo Assets` (PSD/icns/md excluded).*

`detect_bg_color` samples the FOUR CORNER PIXELS and majority-votes. This table compares that answer against the modal exact RGB of a full 8px border ring — a population of tens of thousands of pixels. `dist` is the RGB distance between the two. The run's default `--tolerance` is **15**.

- **3 of 101** images have all four corners agreeing.
- **38 of 101** have the four-corner answer further than the default tolerance from the border mode.

| file | dims | distinct corners | border std | dist | 4-corner pick | border mode | alpha |
|---|---|---|---|---|---|---|---|
| `WIP Renders (Nebula)/Gemini_Generated_Image_1o7bt81o7bt81o7b.jpeg` | 4128x1024 | 4 | 7.49 | **38.7** | (37, 30, 61) | (11, 13, 38) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_5-Gemini_Generated_Image_9mj1uv9mj1uv9mj1.jpeg` | 4160x1024 | 4 | 5.18 | **38.1** | (39, 30, 59) | (13, 13, 37) |  |
| `DEVOID Nebula.png` | 4128x1024 | 4 | 5.30 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `DEVOID Nebula_NoGrid.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v10.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v11.png` | 4128x1024 | 4 | 4.55 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v12.png` | 4128x1024 | 4 | 4.85 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v13.png` | 4128x1024 | 4 | 4.79 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v14.png` | 4128x1024 | 4 | 4.71 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v14b-smoothed.png` | 4128x1024 | 4 | 4.67 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v15.png` | 4128x1024 | 4 | 4.55 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v4.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v5.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v6.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v8.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v9.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid3.png` | 4128x1024 | 4 | 4.53 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_lot5olot5olot5ol.jpeg` | 4128x1024 | 4 | 6.21 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula)/nebula2_grid_faded_more.png` | 4128x1024 | 4 | 5.09 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula)/nebula2_grid_under.png` | 4128x1024 | 4 | 5.30 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula)/nebula2_grid_under_softer.png` | 4128x1024 | 4 | 5.32 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Banner)/devoid_banner.png` | 4128x1024 | 4 | 5.16 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Banner)/devoid_banner_subtle_warp.png` | 4128x1024 | 4 | 4.99 | **35.9** | (32, 30, 54) | (9, 11, 34) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_i43m3ui43m3ui43m.jpeg` | 4128x1024 | 4 | 7.28 | **35.0** | (35, 28, 59) | (12, 12, 38) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_6-Gemini_Generated_Image_ax7192ax7192ax71.jpeg` | 4160x1024 | 4 | 5.33 | **34.5** | (35, 28, 59) | (13, 13, 37) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_4-Gemini_Generated_Image_by68p0by68p0by68.jpeg` | 4160x1024 | 4 | 5.13 | **30.3** | (37, 31, 59) | (19, 17, 39) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_vgmngqvgmngqvgmn.jpeg` | 3584x1184 | 4 | 4.69 | **22.0** | (32, 26, 54) | (19, 15, 40) |  |
| `WIP Renders (Nebula)/Firefly.jpg` | 4249x1259 | 4 | 4.34 | **21.5** | (27, 28, 48) | (16, 14, 36) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_gyyyalgyyyalgyyy.jpeg` | 3584x1184 | 4 | 0.94 | **21.5** | (31, 30, 46) | (19, 16, 35) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_9h3g4u9h3g4u9h3g.jpeg` | 3584x1184 | 4 | 4.84 | **20.3** | (32, 26, 52) | (20, 16, 39) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_2-upscayl_1x-Gemini_Generated_Image_63cufi63cufi63cu.png` | 4160x1024 | 4 | 6.05 | **18.0** | (30, 15, 49) | (15, 15, 39) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_n064b8n064b8n064.jpeg` | 3584x1184 | 4 | 1.40 | **18.0** | (30, 25, 48) | (18, 16, 38) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_vfwba9vfwba9vfwb.jpeg` | 3584x1184 | 4 | 4.22 | **17.4** | (26, 22, 45) | (15, 13, 35) |  |
| `WIP Renders (Nebula)/Firefly (1).jpg` | 4563x1364 | 3 | 6.20 | **17.3** | (27, 23, 46) | (17, 13, 36) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_r8ji4or8ji4or8ji.jpeg` | 3584x1184 | 4 | 0.79 | **17.3** | (24, 20, 43) | (14, 10, 33) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_2-Gemini_Generated_Image_63cufi63cufi63cu.jpeg` | 4160x1024 | 4 | 5.96 | **17.0** | (27, 23, 48) | (15, 15, 39) |  |
| `WIP Renders (Nebula)/DEVOID Nebula_upscayl1x.png` | 4128x1024 | 4 | 7.01 | **15.7** | (19, 18, 43) | (9, 10, 34) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid3_upscayl_1x_digital-art-4x.png` | 4128x1024 | 4 | 4.52 | **15.1** | (19, 18, 43) | (9, 10, 35) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_3-Gemini_Generated_Image_9qi6mc9qi6mc9qi6.jpeg` | 4160x1024 | 4 | 5.98 | **14.1** | (23, 20, 47) | (14, 14, 38) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_3-upscayl_1x-Gemini_Generated_Image_9qi6mc9qi6mc9qi6.png` | 4160x1024 | 4 | 5.91 | **13.3** | (21, 21, 44) | (13, 14, 36) |  |
| `DEVOID Nebula_NoGrid_upscayl1x.png` | 4128x1024 | 4 | 4.52 | **10.5** | (15, 15, 42) | (9, 10, 35) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v4_upscayl_1x.png` | 4128x1024 | 4 | 4.53 | **10.5** | (15, 15, 42) | (9, 10, 35) |  |
| `WIP Renders (Nebula NoGrid)/Claude Attempts/DEVOID_Nebula_nogrid-v6_upscayl_1x.png` | 4128x1024 | 4 | 4.52 | **10.5** | (15, 15, 42) | (9, 10, 35) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_4-upscayl_1x-Gemini_Generated_Image_by68p0by68p0by68.png` | 4160x1024 | 4 | 5.14 | **8.6** | (21, 19, 48) | (18, 18, 40) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_7h8n067h8n067h8n.jpeg` | 4096x1024 | 4 | 6.78 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/nebula_grid_bleed.png` | 4096x1024 | 4 | 6.16 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/nebula_grid_faded.png` | 4096x1024 | 4 | 4.72 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/nebula_grid_faded_more.png` | 4096x1024 | 4 | 4.31 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/nebula_grid_final.png` | 4096x1024 | 4 | 5.27 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/nebula_grid_final_fainter.png` | 4096x1024 | 4 | 4.81 | **8.6** | (17, 12, 42) | (10, 12, 37) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_ldeambldeambldea.jpeg` | 4128x1024 | 4 | 7.01 | **8.3** | (17, 12, 42) | (10, 10, 38) |  |
| `WIP Renders (Wordmark)/Gemini_Generated_Image_73kxcc73kxcc73kx.jpeg` | 1792x592 | 4 | 4.02 | **7.5** | (17, 8, 37) | (13, 14, 35) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_5-upscayl_1x-Gemini_Generated_Image_9mj1uv9mj1uv9mj1.png` | 4160x1024 | 4 | 5.20 | **6.0** | (21, 22, 46) | (19, 18, 42) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_m2eej9m2eej9m2ee.jpeg` | 3786x1120 | 4 | 4.54 | **5.4** | (17, 18, 36) | (19, 15, 40) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_y2bk34y2bk34y2bk.jpeg` | 2048x2048 | 4 | 3.11 | **5.4** | (12, 12, 24) | (9, 8, 22) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_6-upscayl_1x-Gemini_Generated_Image_ax7192ax7192ax71.png` | 4160x1024 | 4 | 5.32 | **4.7** | (22, 22, 44) | (19, 19, 42) |  |
| `Isolated/nebula isolated - extended attempt.jpeg` | 3904x1088 | 4 | 4.65 | **4.5** | (23, 17, 43) | (19, 17, 41) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_mwho0dmwho0dmwho.jpeg` | 2048x2048 | 2 | 5.83 | **4.0** | (9, 8, 22) | (9, 8, 26) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_3qsab93qsab93qsa.jpeg` | 3786x1120 | 4 | 6.78 | **3.7** | (21, 17, 40) | (19, 16, 43) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_cbk1cjcbk1cjcbk1.jpeg` | 1024x1024 | 4 | 5.61 | **3.6** | (10, 7, 28) | (8, 7, 25) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_ye92wuye92wuye92.jpeg` | 1024x1024 | 4 | 6.61 | **3.5** | (9, 9, 17) | (7, 7, 19) |  |
| `WIP Renders (Nebula)/Gemini_Generated_Image_t8nwfat8nwfat8nw.jpeg` | 1792x592 | 4 | 4.34 | **3.2** | (10, 10, 34) | (11, 13, 34) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_ug8sowug8sowug8s.jpeg` | 2048x2048 | 4 | 3.11 | **3.2** | (8, 11, 28) | (11, 10, 28) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_V2_Warp_Vignette_Strong.png` | 3072x1024 | 4 | 5.70 | **2.4** | (10, 10, 28) | (11, 11, 30) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_Vignette_FadeSoft.png` | 3072x1024 | 3 | 5.00 | **2.4** | (10, 9, 29) | (8, 8, 28) |  |
| `DEVOID Banner V1.jpeg` | 3584x1184 | 4 | 4.86 | **2.2** | (19, 13, 39) | (19, 15, 40) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_sfp4d4sfp4d4sfp4.jpeg` | 2048x2048 | 4 | 1.27 | **2.2** | (9, 8, 26) | (9, 6, 27) |  |
| `Isolated/nebula isolated 1.jpeg` | 3584x1184 | 4 | 6.22 | **2.0** | (17, 13, 40) | (17, 13, 38) |  |
| `DEVOID Banner V2_NoWarp.png` | 3072x1024 | 4 | 7.63 | **1.7** | (15, 15, 39) | (14, 14, 38) |  |
| `DEVOID Banner V2_Warp.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) |  |
| `DEVOID Banner V2_Warp_Fade.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 10%T/70%P/256lv |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/Gemini_Attempt_1-Gemini_Generated_Image_sjdzjxsjdzjxsjdz.jpeg` | 4160x1024 | 4 | 5.61 | **1.7** | (15, 15, 41) | (14, 14, 40) |  |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v4.1.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 0%T/74%P/223lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v4.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 7%T/79%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v5.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 5%T/52%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v5_fixed.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 7%T/81%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v6.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 7%T/51%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v6_fixed.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 9%T/79%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v7.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 9%T/50%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v7_fixed.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 11%T/78%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v8.1.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 13%T/48%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v8.1_fixed.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 14%T/74%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v8.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 11%T/49%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v8_fixed.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 12%T/76%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v9.1.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 10%T/70%P/256lv |
| `WIP Renders (Nebula Banner Fade)/DEVOID_Banner_Alpha_Fade_v9.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) | 11%T/78%P/256lv |
| `WIP Renders (Banner)/devoid_banner_3to1_subtler.png` | 3072x1024 | 4 | 7.61 | **1.7** | (15, 15, 39) | (14, 14, 38) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_akzda9akzda9akzd.jpeg` | 1024x1024 | 3 | 0.52 | **1.7** | (15, 16, 36) | (14, 15, 35) |  |
| `Isolated/bg isolated.jpeg` | 3584x1184 | 3 | 4.29 | **1.7** | (17, 15, 39) | (16, 14, 38) |  |
| `Isolated/typeface isolated.png` | 3584x1184 | 4 | 0.49 | **1.7** | (19, 18, 37) | (18, 17, 36) |  |
| `Isolated/vortex isolated.png` | 2048x2048 | 3 | 0.45 | **1.7** | (15, 16, 37) | (14, 15, 36) |  |
| `DEVOID Banner V2_Warp_Vignette.png` | 3072x1024 | 4 | 4.27 | **1.0** | (7, 6, 18) | (7, 6, 19) |  |
| `WIP Renders (Nebula NoGrid)/Gemini Attempts/upscayl_png_1x/Gemini_Attempt_1-upscayl_1x-Gemini_Generated_Image_sjdzjxsjdzjxsjdz.png` | 4160x1024 | 4 | 5.70 | **1.0** | (14, 14, 40) | (13, 14, 40) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_Vignette_Combined.png` | 3072x1024 | 4 | 4.27 | **1.0** | (7, 6, 18) | (7, 6, 19) |  |
| `DEVOID Workmark_BG.png` | 3821x1262 | 1 | 0.00 | **0.0** | (20, 17, 36) | (20, 17, 36) |  |
| `DEVOID Workmark_Transparent.png` | 3821x1262 | 1 | 0.00 | **0.0** | (20, 17, 36) | (20, 17, 36) | 66%T/4%P/256lv |
| `DEVOID app icon.jpeg` | 1024x1024 | 4 | 5.54 | **0.0** | (8, 7, 25) | (8, 7, 25) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_Vignette_Fade.png` | 3072x1024 | 1 | 1.80 | **0.0** | (8, 7, 26) | (8, 7, 26) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_Vignette_Mid.png` | 3072x1024 | 2 | 3.26 | **0.0** | (9, 8, 27) | (9, 8, 27) |  |
| `WIP Renders (Nebula Banner Vignette)/DEVOID_Banner_Vignette_MidPlus.png` | 3072x1024 | 2 | 2.37 | **0.0** | (8, 7, 26) | (8, 7, 26) |  |
| `WIP Renders (App Icon)/Gemini_Generated_Image_mcwao2mcwao2mcwa.jpeg` | 2048x2048 | 4 | 5.50 | **0.0** | (10, 7, 28) | (10, 7, 28) |  |
