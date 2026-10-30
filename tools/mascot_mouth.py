"""Gera as 3 imagens do bico (aberto, meio, fechado) da coruja falando, a partir da coruja de bico aberto.

  python tools/mascot_mouth.py <coruja_recortada.png> frames assets/mascot/talk/f   → f_100, f_45, f_0
  python tools/mascot_mouth.py <coruja_recortada.png> mask preview.png             → confere a área da boca

X0..Y1 e SEED são as coordenadas da boca nessa imagem; ajuste se trocar de mascote.
"""

import sys
import numpy as np
from PIL import Image

X0, X1, Y0, Y1 = 258, 362, 339, 420   # caixa da boca
YEND = 445                            # até onde o queixo "estica"

SEED = (300, 365)                     # ponto dentro da boca (x, y)

def interior_mask(a):
    r, g, b = [a[..., i].astype(int) for i in range(3)]
    yellow = (r > 170) & (g > 110) & (b < 120) & (r - b > 90)
    cream = (r > 190) & (g > 170) & (b > 130)
    clear = a[..., 3] < 128
    ok = ~(yellow | cream | clear)
    m = np.zeros(a.shape[:2], bool)
    stack = [SEED[::-1]]
    while stack:
        y, x = stack.pop()
        if not (Y0 <= y < Y1 and X0 <= x < X1) or m[y, x] or not ok[y, x]:
            continue
        m[y, x] = True
        stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    # fecha buracos pequenos (reflexos) por linha
    for x in range(X0, X1):
        ys = np.where(m[:, x])[0]
        if len(ys):
            m[ys.min():ys.max() + 1, x] = True
    return m

def _smooth(v, n=7):
    v = np.asarray(v, float)
    pad = np.pad(v, (n, n), mode="edge")
    return np.convolve(pad, np.ones(2 * n + 1) / (2 * n + 1), mode="same")[n:-n]


def frame(img, k):
    """k=1 boca aberta (original), k=0 fechada. O espaço que some vira bico de baixo (amarelo)."""
    from PIL import ImageDraw, ImageFilter
    if k >= 1:
        return img.copy()
    a = np.asarray(img).astype(float)
    m = interior_mask(a)
    out = a.copy()
    H = a.shape[0]
    cols = [x for x in range(X0, X1) if m[:, x].sum() >= 2]
    tops = np.array([np.where(m[:, x])[0].min() for x in cols])
    bots = np.array([np.where(m[:, x])[0].max() + 1 for x in cols])
    rims = np.array([a[min(b + 4, H - 1), x, :3] for x, b in zip(cols, bots)])
    base = np.median(rims, axis=0)
    fill = np.zeros(a.shape[:2], bool)
    line = []
    for x, top, bot in zip(cols, tops, bots):
        h = bot - top
        nh = int(round(k * h))
        if nh > 0:  # interior achatado para cima (língua some de baixo pra cima)
            src = top + (np.arange(nh) + 0.5) * h / nh
            out[top:top + nh, x] = a[np.clip(src.astype(int), 0, H - 1), x]
        for i, y in enumerate(range(top + nh, bot + 1)):
            t = i / max(bot - top - nh, 1)
            out[y, x, :3] = base * (0.82 + 0.18 * min(t, 1))  # mais escuro junto ao bico de cima
            out[y, x, 3] = 255
            fill[y, x] = True
        line.append((x, top + nh))
    res = Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")
    # suaviza só a área pintada, com borda esfumada
    soft = Image.fromarray((fill * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
    res = Image.composite(res.filter(ImageFilter.GaussianBlur(2.2)), res, soft)
    # linha da boca (fechada ou meio aberta), suavizada
    xs = np.array([p[0] for p in line]); ys = _smooth(_smooth([p[1] for p in line], 10), 6)
    d = ImageDraw.Draw(res)
    d.line(list(zip(xs.tolist(), ys.tolist())), fill=(110, 50, 25, 255), width=3, joint="curve")
    return res

if __name__ == "__main__":
    src = Image.open(sys.argv[1]).convert("RGBA")
    if sys.argv[2] == "mask":
        a = np.asarray(src); m = interior_mask(a)
        v = a.copy(); v[m] = [0, 255, 0, 255]
        Image.fromarray(v).crop((220, 300, 400, 460)).resize((540, 480)).save(sys.argv[3])
    else:
        for k in (1.0, 0.45, 0.0):
            frame(src, k).save(f"{sys.argv[3]}_{int(k*100)}.png")
