"""
Extract embedded images from Adv_Blockchain_Project_Report.pdf into docs/report_screenshots/.
Usage:
  python extract_report_pdf_images.py "C:\\path\\to\\Adv_Blockchain_Project_Report.pdf"
Requires: pip install pymupdf
"""
import argparse
import os
import shutil
import sys

try:
    import fitz
except ImportError:
    print("Install pymupdf: pip install pymupdf", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Path to the project report PDF")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "docs", "report_screenshots"),
        help="Output directory",
    )
    args = parser.parse_args()

    doc = fitz.open(args.pdf)
    os.makedirs(args.out, exist_ok=True)

    for page_num in range(len(doc)):
        page = doc[page_num]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            fn = os.path.join(args.out, f"pdf_page{page_num + 1:02d}_img{img_index + 1}.png")
            pix.save(fn)
            pix = None

    # Build figure_01..21: pages 6-15 give two figures each; page 16 gives figure 21
    fig = 1
    for p in range(6, 16):
        for m in (1, 2):
            src = os.path.join(args.out, f"pdf_page{p:02d}_img{m}.png")
            dst = os.path.join(args.out, f"figure_{fig:02d}.png")
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                fig += 1
    src = os.path.join(args.out, "pdf_page16_img1.png")
    dst = os.path.join(args.out, "figure_21.png")
    if os.path.isfile(src):
        shutil.copy2(src, dst)

    print(f"Saved extracts under {args.out}")


if __name__ == "__main__":
    main()
