import zipfile, io
from PIL import Image, ImageDraw, ImageFont
ox, oy = 1807, 764                       # IC15 crop origin in the full-res trace image
ys = [70 + 62*i for i in range(16)]       # pad rows, top to bottom
LX, RX = 105, 480                         # left / right pad column x
base = Image.open('d110_traces_bottom.png').convert('RGBA'); w, h = base.size
lab = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(lab)
f = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 30)
def txt(x, y, s, right):
    bb = d.textbbox((0, 0), s, font=f); tw, th = bb[2]-bb[0], bb[3]-bb[1]
    xx = x - tw - 4 if right is False else x + 4
    d.text((xx, y - th/2 - bb[1]), s, font=f, fill=(200, 0, 120, 255), stroke_width=4, stroke_fill=(255, 255, 255, 255))
def name(sst):
    p = sst - 2
    return str(sst)
for i, y in enumerate(ys):
    txt(ox+LX-24, oy+y, name(17+i), False)       # left column, top->bottom = SST 17..32
    txt(ox+RX+24, oy+y, name(16-i), True)        # right column, top->bottom = SST 16..1
out = Image.alpha_composite(base, lab)
out.convert('RGB').save('rosetta_rom/private_banks/d110_traces_bottom_sst.png')
def png(i):
    b = io.BytesIO(); i.save(b, 'PNG'); return b.getvalue()
stack = f'''<?xml version="1.0" encoding="UTF-8"?>
<image version="0.0.3" w="{w}" h="{h}"><stack>
<layer name="SST PIN NUMBERS" src="data/pins.png" opacity="1" visibility="visible" x="0" y="0" composite-op="svg:src-over"/>
<layer name="bottom traces + scan" src="data/base.png" opacity="1" visibility="visible" x="0" y="0" composite-op="svg:src-over"/>
</stack></image>'''
with zipfile.ZipFile('rosetta_rom/private_banks/d110_traces_bottom_sst.ora', 'w') as z:
    z.writestr('mimetype', 'image/openraster', compress_type=zipfile.ZIP_STORED)
    z.writestr('stack.xml', stack); z.writestr('data/base.png', png(base)); z.writestr('data/pins.png', png(lab))
    z.writestr('mergedimage.png', png(out)); t = out.copy(); t.thumbnail((256, 256)); z.writestr('Thumbnails/thumbnail.png', png(t))
out.crop((ox-150, oy-20, ox+700, oy+1200)).convert('RGB').save('rosetta_rom/private_banks/sst_check.png')
