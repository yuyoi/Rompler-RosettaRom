"""Rosetta ROM logo: ice-blue runic ring (ROSETTA in Elder Futhark) round a hollow cross pattee, purple rosette in the
centre ('rosetta' = little rose, and the Rosetta Stone, the key between scripts), purple 'Rosetta' wordmark.
Writes assets/logo.png (transparent), assets/logo_dark.png, assets/logo_mark.png, assets/rosetta.ico"""
import math, os
from PIL import Image, ImageDraw, ImageFont, ImageChops

S = 3                       # supersample
W = 1024; H = 1330; C = (512, 512)
ICE_TOP, ICE_BOT = (222, 247, 255), (74, 170, 220)
PUR_TOP, PUR_BOT = (205, 170, 255), (112, 66, 205)

# Elder Futhark R O S E T T A  (glyph strokes in a 0..1 box, y down)
RUNES = {
    'R': [[(0, 0), (0, 1)], [(0, 0), (0.7, 0.25), (0, 0.5)], [(0, 0.5), (0.75, 1)]],
    'O': [[(0.5, 0), (0.05, 0.33), (0.5, 0.66), (0.95, 0.33), (0.5, 0)], [(0.27, 0.5), (0, 1)], [(0.73, 0.5), (1, 1)]],
    'S': [[(0.75, 0), (0.2, 0.4), (0.8, 0.6), (0.25, 1)]],
    'E': [[(0, 0), (0, 1)], [(1, 0), (1, 1)], [(0, 0), (0.5, 0.42), (1, 0)]],
    'T': [[(0.5, 0), (0.5, 1)], [(0.5, 0), (0, 0.38)], [(0.5, 0), (1, 0.38)]],
    'A': [[(0.1, 0), (0.1, 1)], [(0.1, 0.02), (0.85, 0.32)], [(0.1, 0.32), (0.85, 0.62)]],
}
WORD = 'ROSETTA'


def gradient(size, top, bot):
    g = Image.new('RGB', size); d = ImageDraw.Draw(g); h = size[1]
    for y in range(h):
        t = y / (h - 1); d.line([(0, y), (size[0], y)], fill=tuple(int(top[k] * (1 - t) + bot[k] * t) for k in range(3)))
    return g


def P(x, y): return (x * S, y * S)


def thick_line(d, pts, w, fill=255):
    pts = [P(*p) for p in pts]
    d.line(pts, fill=fill, width=int(w * S), joint='curve')
    r = w * S / 2
    for x, y in pts: d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def ring(d, r, w):
    d.ellipse([P(C[0] - r - w / 2, C[1] - r - w / 2), P(C[0] + r + w / 2, C[1] + r + w / 2)], outline=255, width=int(w * S))


def poly_arm(angle, r0, w0, r1, w1):
    u = (math.sin(angle), -math.cos(angle)); n = (math.cos(angle), math.sin(angle))
    def pt(r, off): return (C[0] + u[0] * r + n[0] * off, C[1] + u[1] * r + n[1] * off)
    return [pt(r0, -w0 / 2), pt(r1, -w1 / 2), pt(r1, w1 / 2), pt(r0, w0 / 2)]


def build_mark():
    ice = Image.new('L', (W * S, W * S), 0); pur = Image.new('L', (W * S, W * S), 0)
    d = ImageDraw.Draw(ice); p = ImageDraw.Draw(pur)
    # rings: rune band between r=292 and r=386
    ring(d, 292, 10); ring(d, 386, 14); ring(d, 400, 4)
    # runes on the band
    R = 339; lh, lw = 68, 46
    for k, ch in enumerate(WORD):
        th = math.radians(k * 360 / 7 + 360 / 14 * 0)   # first letter at top, clockwise
        u = (math.sin(th), -math.cos(th)); n = (math.cos(th), math.sin(th))
        for stroke in RUNES[ch]:
            pts = []
            for x, y in stroke:
                lx = (x - 0.5) * lw; up = (0.5 - y) * lh
                pts.append((C[0] + u[0] * (R + up) + n[0] * lx, C[1] + u[1] * (R + up) + n[1] * lx))
            thick_line(d, pts, 9.5)
        # separator diamond half-way to the next letter
        ph = math.radians((k + 0.5) * 360 / 7); r = R; cx, cy = C[0] + math.sin(ph) * r, C[1] - math.cos(ph) * r
        dm = [(cx, cy - 9), (cx + 6, cy), (cx, cy + 9), (cx - 6, cy)]; d.polygon([P(*q) for q in dm], fill=255)
    # cross pattee: outline + gap + inner fill (engraved / illuminated look), ends stop short of the ring
    def cross_img(off):
        im = Image.new('L', (W * S, W * S), 0); cd = ImageDraw.Draw(im)
        for k in range(4):
            cd.polygon([P(*q) for q in poly_arm(k * math.pi / 2, 30, 70 - 2 * off, 276 - off, 156 - 2 * off)], fill=255)
        cd.rectangle([P(C[0] - 35 + off, C[1] - 35 + off), P(C[0] + 35 - off, C[1] + 35 - off)], fill=255)
        return im
    outline = ImageChops.subtract(cross_img(0), cross_img(10)); core = cross_img(20)
    ice = ImageChops.lighter(ice, ImageChops.lighter(outline, core))
    d = ImageDraw.Draw(ice)
    # pellets in the four quadrants (old manuscript / insular cross)
    for a in range(4):
        ang = math.radians(45 + a * 90)
        for rr, rad in ((205, 11), (165, 8), (130, 6)):
            x, y = C[0] + math.sin(ang) * rr, C[1] - math.cos(ang) * rr
            d.ellipse([P(x - rad, y - rad), P(x + rad, y + rad)], fill=255)
    # purple rosette: 8 petals + eye
    for a in range(8):
        ang = a * math.pi / 4
        pts = []
        for t in range(0, 361, 6):
            tt = math.radians(t); ex, ey = 20 * math.cos(tt), 44 * math.sin(tt)
            lx, ly = ex, ey - 44          # petal base at centre, pointing up (-y)
            rx = lx * math.cos(ang) - ly * math.sin(ang); ry = lx * math.sin(ang) + ly * math.cos(ang)
            pts.append(P(C[0] + rx, C[1] + ry))
        p.polygon(pts, fill=255)
    ice_d = ImageDraw.Draw(ice); ice_d.ellipse([P(C[0] - 11, C[1] - 11), P(C[0] + 11, C[1] + 11)], fill=255)
    # purple cuts a clean gap in the ice cross under the rosette
    gap = Image.new('L', (W * S, W * S), 0); ImageDraw.Draw(gap).ellipse([P(C[0] - 58, C[1] - 58), P(C[0] + 58, C[1] + 58)], fill=255)
    ice = ImageChops.subtract(ice, ImageChops.subtract(gap, Image.new('L', gap.size, 0)))
    ice_d = ImageDraw.Draw(ice); ice_d.ellipse([P(C[0] - 11, C[1] - 11), P(C[0] + 11, C[1] + 11)], fill=255)
    return ice, pur


def compose(ice, pur, wordmark=True, bg=None):
    size = (W, H if wordmark else W)
    canvas = Image.new('RGBA', size, bg or (0, 0, 0, 0))
    ice_s = ice.resize((W, W), Image.LANCZOS); pur_s = pur.resize((W, W), Image.LANCZOS)
    canvas.paste(Image.merge('RGBA', (*gradient((W, W), ICE_TOP, ICE_BOT).split(), ice_s)), (0, 0), ice_s)
    canvas.paste(Image.merge('RGBA', (*gradient((W, W), PUR_TOP, PUR_BOT).split(), pur_s)), (0, 0), pur_s)
    if wordmark:
        wm = Image.new('L', (W * S, 360 * S), 0); d = ImageDraw.Draw(wm)
        f = ImageFont.truetype('C:/Windows/Fonts/gabriola.ttf', 270 * S)
        bb = d.textbbox((0, 0), 'Rosetta', font=f); x = (W * S - (bb[2] - bb[0])) // 2 - bb[0]
        d.text((x, 10 * S - bb[1] + 20 * S), 'Rosetta', font=f, fill=255)
        wm = wm.resize((W, 360), Image.LANCZOS)
        canvas.paste(Image.merge('RGBA', (*gradient((W, 360), PUR_TOP, PUR_BOT).split(), wm)), (0, 975), wm)
        rm = Image.new('L', (W * S, 90 * S), 0); d = ImageDraw.Draw(rm)
        f2 = ImageFont.truetype('C:/Windows/Fonts/cambriab.ttf', 54 * S)
        txt = 'R  O  M'; bb = d.textbbox((0, 0), txt, font=f2); d.text(((W * S - (bb[2] - bb[0])) // 2 - bb[0], 10 * S), txt, font=f2, fill=255)
        rm = rm.resize((W, 90), Image.LANCZOS)
        canvas.paste(Image.merge('RGBA', (*gradient((W, 90), ICE_TOP, ICE_BOT).split(), rm)), (0, 1222), rm)
    return canvas


if __name__ == '__main__':
    os.makedirs('assets', exist_ok=True)
    ice, pur = build_mark()
    compose(ice, pur, True).save('assets/logo.png')
    compose(ice, pur, True, (18, 22, 26, 255)).save('assets/logo_dark.png')
    mark = compose(ice, pur, False); mark.save('assets/logo_mark.png')
    icon_bg = compose(ice, pur, False, (29, 34, 40, 255))
    icon_bg.save('assets/rosetta.ico', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print('ok')
