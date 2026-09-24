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


if __name__ == '__main__':
    unittest.main()
