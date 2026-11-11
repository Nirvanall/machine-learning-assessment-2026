"""Render the matching PDF and check deck bounds, notes and slide counts."""
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw
from pptx import Presentation

OUT=Path(__file__).resolve().parents[1]
previews=OUT/'previews';previews.mkdir(exist_ok=True)
doc=pymupdf.open(OUT/'steam_management_presentation_dev_prod.pdf')
prs=Presentation(OUT/'steam_management_presentation_dev_prod.pptx')
assert len(doc)==len(prs.slides)==15
images=[]
for i,page in enumerate(doc):
    path=previews/f'slide-{i+1:02}.png'
    page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(str(path))
    im=Image.open(path).convert('RGB');im.thumbnail((640,360));images.append(im.copy())
    assert page.get_text().strip()
    assert prs.slides[i].notes_slide.notes_text_frame.text.strip()
    for shape in prs.slides[i].shapes:
        assert shape.left>=0 and shape.top>=0
        assert shape.left+shape.width<=prs.slide_width+12700
        assert shape.top+shape.height<=prs.slide_height+12700
for offset in range(0,len(images),7):
    sheet=Image.new('RGB',(1300,1560),'#e7e9e5');draw=ImageDraw.Draw(sheet)
    for j,im in enumerate(images[offset:offset+7]):
        x=10+(j%2)*650;y=10+(j//2)*390
        sheet.paste(im,(x,y));draw.text((x+7,y+364),f'Slide {offset+j+1:02}',fill='#172b2a')
    sheet.save(previews/f'contact-sheet-{offset//7+1}.png')
print('Validated 15 slides and notes; rendered previews and contact sheets.')
