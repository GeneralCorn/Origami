"""Render a labelled set of synthetic iPhone screenshots, one folder per collection id.

A stand-in for real captures when none are to hand: each image has the
status bar, a back control and a tab bar around text of the kind a real
screen of that collection carries. It is the input behind the numbers in
docs/SCREENSHOT_PIPELINE.md and it exists so that anyone can reproduce
them. It is not a substitute for real screenshots: the layouts are
uniform and the OCR reads them perfectly, so the OCR half of the pipeline
is barely tested here. Tune the classifier on your own captures.

Run from backend/ so Pillow is on the path, then score the result:

    uv run python ../scripts/render_sample_screenshots.py ../sample-screenshots
    uv run python ../scripts/eval_screenshot_classifier.py ../sample-screenshots
"""

import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
WIDTH, HEIGHT = 1179, 2556

SAMPLES: dict[str, list[tuple[str, list[str]]]] = {
    "shows-to-watch": [
        ("netflix-severance", ["Severance", "2022 · TV-MA · 2 Seasons · Thriller", "Mark leads a team of office workers whose memories have been surgically divided between their work and personal lives.", "Starring: Adam Scott, Britt Lower, John Turturro", "Play", "My List"]),
        ("letterboxd-pastlives", ["Past Lives", "2023 · Directed by Celine Song", "★★★★½ 4.3", "Nora and Hae Sung, two deeply connected childhood friends, are wrested apart after Nora's family emigrates from South Korea.", "Watched", "Add to watchlist"]),
        ("crunchyroll-frieren", ["Frieren: Beyond Journey's End", "Season 1 · 28 Episodes · Sub | Dub", "The adventure is over but life goes on for an elf mage just beginning to learn what living is all about.", "Start Watching"]),
    ],
    "tech-to-try": [
        ("github-uv", ["astral-sh / uv", "An extremely fast Python package and project manager, written in Rust.", "★ 48.2k   Fork 1.4k", "pip install uv", "README · MIT license"]),
        ("bun-release", ["Bun v1.2 release notes", "Built-in S3 client, Postgres driver, and a 30% faster install", "bun upgrade", "Changelog · Docs"]),
        ("hn-zed", ["Show HN: Zed, a high-performance code editor written in Rust", "Open source, GPU-accelerated, collaborative editing built in", "brew install --cask zed", "412 points · 187 comments"]),
    ],
    "markets-to-watch": [
        ("robinhood-nvda", ["NVDA", "NVIDIA Corporation", "$875.40", "+$27.12 (+3.20%) Today", "Market cap 2.15T · P/E ratio 74.2", "After hours $876.10", "Buy", "Sell"]),
        ("fed-news", ["Fed holds rates steady, signals two cuts in 2026", "S&P 500 4,912.45 +0.8%", "Nasdaq 15,678.90 +1.2%", "10-year Treasury yield 4.12%", "Markets · 2 hours ago"]),
        ("coinbase-btc", ["BTC", "Bitcoin", "$67,432.10", "+2.4% 24h", "Volume $32.1B · Market cap $1.3T", "ETH $3,512.55 +1.1%"]),
    ],
    "papers-to-read": [
        ("arxiv-ssm", ["arXiv:2401.12345 [cs.CL]", "Attention Is Not All You Need: Rethinking Sequence Models", "Jane Doe, John Smith, et al.", "Abstract: We propose a state-space alternative to self-attention that scales linearly in sequence length while matching transformer quality on long-context benchmarks.", "Submitted 22 Jan 2026", "PDF"]),
        ("neurips-rag", ["NeurIPS 2025 · Oral", "Scaling Laws for Retrieval-Augmented Generation", "University of Toronto · Vector Institute", "Our results show that retrieval quality dominates model size beyond 7B parameters across all evaluated domains.", "Citation · DOI 10.1000/xyz123"]),
        ("s2-dpo", ["Direct Preference Optimization: Your Language Model is Secretly a Reward Model", "Rafailov et al. 2023 · 4,120 citations", "Abstract: While large-scale unsupervised language models learn broad world knowledge and some reasoning skills, achieving precise control of their behavior is difficult."]),
    ],
    "places-to-go": [
        ("gmaps-barraval", ["Bar Raval", "4.6 ★ (2,341 reviews) · $$ · Tapas bar", "505 College St, Toronto, ON", "Open · Closes 2 AM", "Directions", "Call", "Save"]),
        ("yelp-kissatanto", ["Kissa Tanto", "4.5 ★ 812 reviews · Japanese, Italian", "263 E Pender St, Vancouver, BC", "Reservation recommended · Dinner only", "Menu", "Reviews"]),
        ("airbnb-cabin", ["Cabin with lake view", "Muskoka, Ontario · 2.1 miles away", "$210 night · Aug 14 - 17", "Check-in 3 PM · Check-out 11 AM", "4.92 ★ · Superhost"]),
    ],
    "recipes-to-cook": [
        ("garlic-chicken", ["Garlic Butter Chicken Thighs", "Servings 4 · Prep 10 min · Cook 25 min", "Ingredients", "6 bone-in chicken thighs", "3 tbsp butter", "4 cloves garlic, minced", "1 tsp paprika", "Preheat oven to 425°F"]),
        ("tomato-pasta", ["One-Pot Tomato Basil Pasta", "Ingredients: 12 oz spaghetti, 1 can crushed tomatoes, 1 onion, 2 cups vegetable broth", "Simmer 12 minutes, stirring occasionally", "Season with salt and pepper", "Save recipe"]),
        ("miso-salmon", ["Miso Glazed Salmon", "2 tbsp white miso · 1 tbsp mirin · 1 tsp soy sauce", "Whisk the glaze and marinate 20 minutes", "Bake 12 minutes at 400°F", "4 servings"]),
    ],
    "inbox": [
        ("imessage-sarah", ["Sarah", "hey are we still on for tonight?", "yeah 7 works", "ok see you there", "iMessage"]),
        ("weather-toronto", ["Toronto", "21°", "Partly Cloudy", "H:24° L:15°", "Hourly forecast"]),
    ],
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONTS:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render(lines: list[str], path: Path) -> None:
    """One phone screen: status bar, back control, the lines, a tab bar."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = _font(64), _font(44), _font(36)
    draw.text((90, 40), "9:41", fill="black", font=small_font)
    draw.text((WIDTH - 260, 40), "5G  100%", fill="black", font=small_font)
    draw.text((60, 150), "‹ Back", fill="black", font=body_font)
    y = 300
    for index, line in enumerate(lines):
        font = title_font if index == 0 else body_font
        for wrapped in textwrap.wrap(line, 30 if index == 0 else 44) or [""]:
            draw.text((80, y), wrapped, fill="black", font=font)
            y += 95 if index == 0 else 70
        y += 40
    for x, label in zip((120, 400, 680, 960), ("Home", "Search", "Library", "Profile")):
        draw.text((x, HEIGHT - 130), label, fill="black", font=small_font)
    image.save(path)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    count = 0
    for collection, shots in SAMPLES.items():
        folder = root / collection
        folder.mkdir(parents=True, exist_ok=True)
        for name, lines in shots:
            render(lines, folder / f"{name}.png")
            count += 1
    print(f"rendered {count} screenshots under {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
