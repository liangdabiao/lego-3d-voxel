"""程序化体素生成：没有 3D 模型文件时，用基本形拼出形体，再按一格一砖装配。

适用场景（实测只有这一种值得走这条路）：
**参考图本身就是体素风/像素风**——块面清楚、色块分明。这时"对着图造型再逐格生成"
比"找模型切片"更准，因为根本没有模型可切，而目测法（照片取色、凭感觉捏形体）已被用户否决。

用法：

    python gen.py --scene examples/whale-island.py --out work/volume.json

场景文件是一个普通 Python 文件，必须提供 `build(v)`，用 v 的方法把格子写进去：

    def build(v):
        v.revolve(0, 0, [6, 5, 4, 2], top_y=0, color=grass_and_dirt)
        v.ellipsoid(0, 6, 0, 6.4, 4.1, 3.7, 'Blue')
        v.put(-4, 7, 3, 'Black')

坐标约定（与 vox.py 一致）：
  x = 左右，y = 砖层（1 格 = 1 块 1×1×3 砖），z = 前后（+z = 正面）。
  基本形的中心/半径都用"格索引"为单位；判断时用格中心 (x+0.5, y+0.5, z+0.5)。

输出 volume.json 与 vox.py 完全相同，后续 preview.py / downscale.py / build.mjs 照常用。

为什么不用随机数：hash01 是坐标的确定函数，同一个场景文件任何时候跑出来都是同一份体素，
改一个参数、重跑、对比差异这种"改一处验一次"的流程才成立。
"""
import argparse
import json
import math
import runpy
import sys
from collections import Counter

# 15 色板里"自然场景"最常用的几色，写在这里只是提示，不是白名单：
#   草皮/树冠  Green · Bright Green · Lime
#   泥土/岩层  Reddish Brown · Dark Brown
#   水/主体    Blue · Medium Blue · Dark Blue
#   肚皮/沙    Tan · Dark Tan
#   小件      White · Black · Yellow · Bright Light Orange


def hash01(x, y, z, salt=0):
    """稳定伪随机：(x,y,z,salt) 相同就永远同一个值。用来做草皮杂色、岩层杂色。"""
    n = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (salt * 2654435761)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


class Vox:
    def __init__(self):
        self.cells = {}

    # ------------------------------------------------------------ 写格子
    def put(self, x, y, z, c, overwrite=True):
        k = (int(x), int(y), int(z))
        if overwrite or k not in self.cells:
            self.cells[k] = c

    def box(self, x0, y0, z0, x1, y1, z1, c):
        """闭区间实心块。"""
        for x in range(int(x0), int(x1) + 1):
            for y in range(int(y0), int(y1) + 1):
                for z in range(int(z0), int(z1) + 1):
                    self.put(x, y, z, c)

    # ------------------------------------------------------------ 测试形
    def inside_ellipsoid(self, x, y, z, cx, cy, cz, rx, ry, rz):
        px, py, pz = x + 0.5, y + 0.5, z + 0.5
        return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 + ((pz - cz) / rz) ** 2 <= 1.0

    def ellipsoid(self, cx, cy, cz, rx, ry, rz, c):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
                for z in range(int(cz - rz) - 1, int(cz + rz) + 2):
                    if self.inside_ellipsoid(x, y, z, cx, cy, cz, rx, ry, rz):
                        self.put(x, y, z, c)

    def revolve(self, cx, cz, radii, top_y, color):
        """由上往下的半径剖面 → 旋转体（浮空岛/树干/塔身）。

        radii[0] 是最上面一层（草皮平台），往下逐层收。color(x, y, z, d, r, i) 返回色名，
        d = 该格到轴心的水平距离，r = 当前层半径，i = 层号（0 = 顶面）。
        """
        for i, r in enumerate(radii):
            y = top_y - i
            rr = int(math.ceil(r))
            for x in range(int(math.floor(cx - rr)), int(math.ceil(cx + rr)) + 1):
                for z in range(int(math.floor(cz - rr)), int(math.ceil(cz + rr)) + 1):
                    d = math.hypot(x + 0.5 - cx, z + 0.5 - cz)
                    if d > r:
                        continue
                    self.put(x, y, z, color(x, y, z, d, r, i))

    def tube(self, path, radius, c):
        """沿一串节点铺一根粗管：每格填曼哈顿距离 ≤ radius 的邻域。

        path 是 [(x,y,z), ...]，节点不用连续——中间靠邻域重叠接上即可。
        躯干、尾巴、四肢、树干都能用；radius=0 就是逐格画线。
        """
        for (px, py, pz) in path:
            px, py, pz = int(px), int(py), int(pz)
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if abs(dx) + abs(dy) + abs(dz) <= radius:
                            self.put(px + dx, py + dy, pz + dz, c)

    # ------------------------------------------------------------ 改色
    def repaint(self, pred, c, only=None):
        """只换颜色、不动几何。pred(x, y, z) 为真且（only 为空或原色在 only 里）就改。"""
        for k, old in list(self.cells.items()):
            if only is not None and old not in only:
                continue
            if pred(*k):
                self.cells[k] = c

    # ------------------------------------------------------------ 输出
    def bounds(self):
        xs = [c[0] for c in self.cells]
        ys = [c[1] for c in self.cells]
        zs = [c[2] for c in self.cells]
        return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)

    def save(self, path, up='y', front='z', cam=None):
        """平移到非负坐标后写 volume.json（与 vox.py 同格式）。"""
        x0, y0, z0, x1, y1, z1 = self.bounds()
        cells = [[x - x0, y - y0, z - z0, c] for (x, y, z), c in sorted(self.cells.items())]
        out = {
            'nx': x1 - x0 + 1,
            'ny': y1 - y0 + 1,
            'nz': z1 - z0 + 1,
            'up': up,
            'front': front,
            'cells': cells,
        }
        if cam is not None:
            out['cam'] = cam
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
        return out

    def stats(self):
        return len(self.cells), Counter(self.cells.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scene', help='场景文件（提供 build(v)）')
    ap.add_argument('--out', required=True, help='输出 volume.json')
    ap.add_argument('--check', action='store_true', help='只统计已有 volume.json')
    a = ap.parse_args()

    if a.check:
        V = json.load(open(a.out, encoding='utf-8'))
        cnt = Counter(c[3] for c in V['cells'])
        print('grid %d x %d x %d  |  cells %d  |  colours %d'
              % (V['nx'], V['ny'], V['nz'], len(V['cells']), len(cnt)))
        for name, n in cnt.most_common():
            print('  %-22s %5d  %4.1f%%' % (name, n, 100.0 * n / len(V['cells'])))
        return

    if not a.scene:
        sys.exit('需要 --scene（或 --check 只统计）')

    ns = runpy.run_path(a.scene)
    if 'build' not in ns:
        sys.exit('%s 里没有 build(v)' % a.scene)

    v = Vox()
    ns['build'](v)
    out = v.save(a.out)
    n, cnt = v.stats()
    print('grid %d x %d x %d  |  cells %d  |  colours %d  |  courses %d'
          % (out['nx'], out['ny'], out['nz'], n, len(cnt), out['ny']))
    print('colours', cnt.most_common(12))
    print('wrote', a.out)


if __name__ == '__main__':
    main()
