import unittest
from app.seedance import extract_prompt_search_snippets

SAMPLE_FOLDER_44_PROMPT = """44 - น้ำอาบไหลช้าน่าหงุดหงิดใช้หัวฝักบัวแรงดันสูง

Attach the product image as @product. Use @product as the strict visual reference for the product shown in the product insert section.

Vertical 9:16 ultra-realistic cinematic Thai social drama video with spoken Thai dialogue, 10 seconds, handheld phone-video energy, polished AI realism. Setting: a modern Thai home bathroom — white subway tiles, a rain-glass shower enclosure, shampoo bottles lined on a shelf, soft morning light filtering through frosted glass. Characters: a handsome Thai boyfriend in his late 20s standing outside the shower in a towel looking frustrated, and his beautiful Thai girlfriend in her mid-20s in casual homewear holding a new showerhead box — both attractive adults, fictional characters, no celebrity references.

Dialogue & Audio Style: Authentic spoken Thai language dialogue. Natural mouth sync, clear spoken Thai, frustrated-then-amazed pacing. Dramatic contrast between weak trickle sound and powerful rushing water sound.

0:00-0:02 — Boyfriend stands at the shower, water dribbling weakly from the old showerhead in a pathetic trickle. He slaps the pipe in frustration and turns to his girlfriend, eyebrows furrowed: "น้ำมันไหลช้ามากเลย อาบแบบนี้ไม่มีวันเสร็จ!"

0:02-0:04 — Girlfriend smirks, pulls out a high-pressure showerhead from behind her back, and quickly swaps it onto the fitting with confident hands. She steps aside and gestures for him to try: "ลองเปิดดูสิ อันใหม่ที่หนูซื้อมา แรงดันสูงพิเศษเลย!"

0:04-0:07 — ASMR macro insert: extreme close-up of @product — the sleek chrome high-pressure showerhead mounted on the fitting, water pressure building then ERUPTING in a powerful symmetrical fan of fine jets. Water droplets catch the light like diamonds, steam curls up in slow-motion. The spray pattern fills the frame edge to edge, each jet perfectly parallel. Rich, thunderous water-rush audio fills the soundscape. Shallow focus on the chrome nozzle face.

0:07-0:10 — Boyfriend leans into the powerful spray, head tilted back, eyes closed in bliss, water cascading over his face. He turns to the camera over his shoulder, grinning wide: "โห! อันนี้มันคนละเรื่องเลย ดีมากกกก!"

Style requirements: romantic couple bathroom drama, clean white-tile morning bathroom aesthetic, attractive Thai couple with authentic spoken Thai dialogue, thunderous ASMR water-pressure macro insert, shallow depth of field, natural handheld micro-shake, vertical social-media composition, strictly zero on-screen text.

Negative constraints: no kids, no children, no text, no subtitles, no words, no letters, no on-screen text, no text overlays, no floating UI, no cartoon, no CGI toy look, no fantasy, no browser screen, no watermarks, no readable product labels, no gore, no over-smooth plastic skin, no non-Thai facial features as main characters."""


class TestSeedanceMatcher(unittest.TestCase):
    def test_extract_snippets_excludes_boilerplate(self):
        snippets = extract_prompt_search_snippets(SAMPLE_FOLDER_44_PROMPT)
        self.assertGreater(len(snippets), 0)

        forbidden = [
            "attach the product image as @product",
            "strict visual reference",
            "vertical 9:16",
            "ultra-realistic",
            "dialogue & audio style",
            "style requirements",
            "negative constraints"
        ]
        for s in snippets:
            s_lower = s.lower()
            for fb in forbidden:
                self.assertNotIn(fb, s_lower, f"Boilerplate '{fb}' leaked into snippet: '{s}'")

    def test_extract_snippets_includes_title_and_dialogue(self):
        snippets = extract_prompt_search_snippets(SAMPLE_FOLDER_44_PROMPT)
        self.assertTrue(any("44 - น้ำอาบ" in s for s in snippets), "Folder title snippet missing")
        self.assertTrue(any("น้ำมันไหลช้ามากเลย" in s for s in snippets), "Dialogue 1 missing")
        self.assertTrue(any("ลองเปิดดูสิ" in s for s in snippets), "Dialogue 2 missing")
        self.assertTrue(any("โห! อันนี้มันคนละเรื่องเลย" in s for s in snippets), "Dialogue 3 missing")

    def test_disaster_prompts_differentiation(self):
        p1 = "Photorealistic raw eyewitness footage, vertical 9:16 miniature coastal town tsunami scene featuring two separate groups of terrified tiny Asian human civilians of varied ages facing a colossal dark green tsunami wall surging inland and swallowing miniature harbour buildings whole, believable scale contrast against a real human hand... 0-2s: the tsunami wall roars forward at full force inches from engulfing both groups..."
        p2 = "Photorealistic raw eyewitness footage, vertical 9:16 miniature city flash flood scene featuring two separate groups of terrified tiny Asian human civilians of varied ages facing a violent brown flash flood torrent ripping through narrow downtown streets and hurling parked miniature cars like toys, believable scale contrast against a real human hand... 0-2s: the flash flood tears down the street at full force inches from sweeping both groups away..."

        snips1 = extract_prompt_search_snippets(p1)
        snips2 = extract_prompt_search_snippets(p2)

        # Ensure no common generic prefix like "Photorealistic raw eyewitness" is extracted
        for s in snips1 + snips2:
            self.assertFalse(s.lower().startswith("photorealistic raw eyewitness"), f"Generic prefix leaked: {s}")

        # Ensure distinctive disaster keywords are present
        self.assertTrue(any("tsunami" in s.lower() for s in snips1), "Tsunami phrase missing from p1")
        self.assertTrue(any("flash flood" in s.lower() for s in snips2), "Flash flood phrase missing from p2")

        # Ensure p1 snippets do not match p2 and vice versa
        self.assertFalse(any("flash flood" in s.lower() for s in snips1), "Cross-contamination: flash flood in p1")
        self.assertFalse(any("tsunami" in s.lower() for s in snips2), "Cross-contamination: tsunami in p2")

    def test_dwarf_preset_boilerplate_filtering(self):
        prompt_dwarf = """Preset คนแคระ Dwarf Fantasy Animation Scene
0-2s: คนแคระช่างตีเหล็กกำลังทุบค้อนลงบนดาบทองคำประกายไฟสว่างจ้า
2-4s: คนแคระยกดาบขึ้นส่องดูความคมด้วยรอยยิ้มภาคภูมิใจ
Style requirements: dwarf fantasy, photorealistic vertical 9:16 seedance dreamina video."""
        snippets = extract_prompt_search_snippets(prompt_dwarf)
        for s in snippets:
            s_lower = s.lower()
            self.assertNotEqual(s_lower, "คนแคระ", "Bare preset name leaked as snippet")
            self.assertNotEqual(s_lower, "dwarf", "Bare preset name leaked as snippet")
            self.assertFalse(s_lower.startswith("preset"), "Preset prefix leaked as snippet")
        # Ensure meaningful action is extracted
        self.assertTrue(any("ช่างตีเหล็ก" in s for s in snippets), "Action snippet missing")


    def test_strict_discrimination_unrelated_prompts(self):
        # Folder 6 chemical spill prompt vs online toddler spoon card
        folder_6_prompt = "Photorealistic raw eyewitness footage, vertical 9:16 miniature human disaster scene featuring two separate groups of terrified tiny Asian human civilians facing a catastrophic toxic chemical spill where a massive overturned tanker truck hemorrhages a surging luminous neon-green corrosive chemical tide... 0-2s: The toxic chemical wave surges forward in a fast-moving glowing green river..."
        online_toddler_card = "139 Duration: 15 seconds Use attached character references for identity continuity if available: @img1 = toddler / small child @img2 = father @img3 = mother A toddler picks up a large spoon, points it at the TV like a remote control, and begins pressing the buttons on the spoon handle..."

        snips_f6 = extract_prompt_search_snippets(folder_6_prompt)
        # Ensure none of the folder 6 snippets exist in the toddler card
        for snip in snips_f6:
            if len(snip) >= 20:
                self.assertNotIn(snip.lower(), online_toddler_card.lower(), f"Snippet falsely appeared in card: {snip}")

    def test_exact_character_match_without_newlines(self):
        local_p = """Photorealistic raw eyewitness footage, vertical 9:16
miniature building facade collapse scene
featuring two separate groups of terrified tiny Asian human civilians..."""
        card_p = "Photorealistic raw eyewitness footage, vertical 9:16 miniature building facade collapse scene featuring two separate groups of terrified tiny Asian human civilians..."
        def compact(s):
            return "".join(s.split()).lower()
        self.assertEqual(compact(local_p), compact(card_p))


if __name__ == '__main__':
    unittest.main()
