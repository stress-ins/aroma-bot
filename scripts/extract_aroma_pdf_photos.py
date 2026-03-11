from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = Path("/Users/p.kutsenko/Downloads")
OUTPUT_DIR = ROOT / "assets" / "reference_images" / "aromas"

# Crop parameters tuned against the current PDF layout exported from the oil cards.
THUMB_SIZE = "1200"
CROP_HEIGHT = "205"
CROP_WIDTH = "320"
CROP_OFFSET_Y = "42"
CROP_OFFSET_X = "548"

PDF_BY_SLUG = {
    "orange": "АПЕЛЬСИН.pdf",
    "basil": "БАЗИЛИК.pdf",
    "bergamot": "БЕРГАМОТ.pdf",
    "helichrysum": "БЕССМЕРТНИК.pdf",
    "vetiver": "ВЕТИВЕР.pdf",
    "clove": "ГВОЗДИКА.pdf",
    "geranium": "ГЕРАНЬ.pdf",
    "grapefruit": "ГРЕЙПФРУТ.pdf",
    "jasmine": "ЖАСМИН.pdf",
    "ylang-ylang": "ИЛАНГ-ИЛАНГ.pdf",
    "ginger": "ИМБИРЬ.pdf",
    "cedarwood": "КЕДР.pdf",
    "cypress": "КИПАРИС.pdf",
    "copaiba": "КОПАИБА.pdf",
    "cinnamon": "КОРИЦА.pdf",
    "lavender": "ЛАВАНДА.pdf",
    "frankincense": "ЛАДАН.pdf",
    "lime": "ЛАЙМ.pdf",
    "lemongrass": "ЛЕМОНГРАСС.pdf",
    "lemon": "ЛИМОН.pdf",
    "marjoram": "МАЙОРАН.pdf",
    "mandarin": "МАНДАРИН.pdf",
    "juniper": "МОЖЖЕВЕЛЬНИК.pdf",
    "clary-sage": "ШАЛФЕЙ МУСКАТНЫЙ.pdf",
    "peppermint": "МЯТА ПЕРЕЧНАЯ.pdf",
    "neroli": "НЕРОЛИ.pdf",
    "patchouli": "ПАЧУЛИ.pdf",
    "balsam-fir": "ПИХТА БАЛЬЗАМИЧЕСКАЯ.pdf",
    "rose": "РОЗА.pdf",
    "rosemary": "РОЗМАРИН.pdf",
    "german-chamomile": "РОМАШКА ГЕРМАНСКАЯ.pdf",
    "sandalwood": "САНДАЛ.pdf",
    "thyme": "ТИМЬЯН.pdf",
    "fennel": "ФЕНХЕЛЬ.pdf",
    "citronella": "ЦИТРОНЕЛЛА.pdf",
    "tea-tree": "ЧАЙНОЕ ДЕРЕВО.pdf",
    "eucalyptus-globulus": "ЭВКАЛИПТ.pdf",
}


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    if shutil.which("qlmanage") is None or shutil.which("sips") is None:
        print("qlmanage and sips are required", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="aroma-pdf-thumbs-") as tmp:
        tmpdir = Path(tmp)
        for slug, filename in PDF_BY_SLUG.items():
            pdf_path = DOWNLOADS / filename
            if not pdf_path.exists():
                skipped.append(filename)
                continue

            _run(["qlmanage", "-t", "-s", THUMB_SIZE, "-o", str(tmpdir), str(pdf_path)])
            thumb_path = tmpdir / f"{pdf_path.name}.png"
            if not thumb_path.exists():
                skipped.append(filename)
                continue

            output_path = OUTPUT_DIR / f"{slug}.png"
            _run(
                [
                    "sips",
                    "-c",
                    CROP_HEIGHT,
                    CROP_WIDTH,
                    "--cropOffset",
                    CROP_OFFSET_Y,
                    CROP_OFFSET_X,
                    str(thumb_path),
                    "--out",
                    str(output_path),
                ]
            )
            created += 1

    print(f"created {created} images")
    if skipped:
        print("skipped:")
        for name in skipped:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
