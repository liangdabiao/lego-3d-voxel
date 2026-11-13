"""蓝鲸浮岛 —— 程序化体素的最小完整例子。

参考图：一只体素风的蓝鲸坐在浮空草岛上，奶油色肚皮、上扬的 V 形尾鳍、两只胸鳍，
岛上有两棵棕榈树和一个发光小灯。图本身是体素化的，所以不走"切片"，直接生成。

跑法：
    python scripts/gen.py --scene examples/whale-island.py --out work/volume.json
    python scripts/preview.py --vol work/volume.json --outdir work

实测结果：19 × 22 × 16 格、1,265 格、430 件、11 色、33 处未连接。
这个文件同时是"参数怎么调"的参照：下面每个数字都是调图调出来的，注释写了为什么。
"""


def build(v):
    # ------------------------------------------------------------ 浮空岛
    # 由上往下的半径剖面：顶面比鲸身略宽（否则鲸鱼两侧悬空），往下收成尖。
    # 岛越大，鲸鱼看起来越小；这套半径是"鲸鱼坐满岛面"的比例。
    radii = [6.7, 6.6, 6.0, 5.2, 4.3, 3.3, 2.2, 1.1]

    def island_color(x, y, z, d, r, i):
        n = v_hash(x, y, z, 7)
        if i == 0:                                   # 草皮顶面：主绿 + 少量浅绿 + 极少量黄绿
            return 'Lime' if n > 0.82 else ('Bright Green' if n > 0.16 else 'Green')
        if i == 1:                                   # 侧面：外圈草、内圈土
            return 'Green' if d > r - 1.8 else 'Reddish Brown'
        if i <= 3:                                   # 土层
            return 'Reddish Brown' if v_hash(x, y, z, 3) > 0.28 else 'Dark Brown'
        return 'Dark Brown' if v_hash(x, y, z, 5) > 0.18 else 'Reddish Brown'

    v.revolve(0, 0, radii, top_y=0, color=island_color)

    # ------------------------------------------------------------ 鲸身
    # 主体椭球 + 前半部一个更钝的"方头"截面，才像鲸而不是蛋。
    # CY 决定鲸鱼坐多高：太低会陷进草皮，太高会浮在岛上方。6.3 是坐稳的值。
    cx, cy, cz = 0.5, 6.3, 0.5
    rx, ry, rz = 6.4, 4.1, 3.7

    body = []
    for x in range(-11, 14):
        for y in range(0, 15):
            for z in range(-9, 10):
                if v.inside_ellipsoid(x, y, z, cx, cy, cz, rx, ry, rz):
                    body.append((x, y, z))
                    continue
                px, py, pz = x + 0.5, y + 0.5, z + 0.5
                if -7.8 <= px <= -1.5:               # 方头：从前端到肩部，截面越往后越大
                    t = (px + 7.8) / 6.3             # 0 = 鼻尖，1 = 肩部
                    hry, hrz = 3.0 + 1.2 * t, 3.3 + 1.0 * t
                    if ((py - cy) / hry) ** 2 + ((pz - cz) / hrz) ** 2 <= 1.0:
                        body.append((x, y, z))

    for (x, y, z) in body:
        v.put(x, y, z, 'Blue')

    # 肚皮：前下方一片椭圆，边界跟着身体的弧走。范围小了像补丁，大了吃进侧身。
    v.repaint(lambda x, y, z: ((x + 0.5 + 3.0) / 5.4) ** 2 + ((y + 0.5 - 3.0) / 3.8) ** 2 <= 1.0
              and y + 0.5 < cy + 1.2, 'Tan', only={'Blue'})

    # 背脊极少量暗蓝：只用来提示体积。撒多了整条背会变成噪点（试过 0.55 阈值，太花）。
    v.repaint(lambda x, y, z: y >= cy + 3.4 and v_hash(x, y, z, 11) > 0.85, 'Medium Blue', only={'Blue'})

    # 眼睛：一格黑 + 一格白高光就够。放大到 2×2 会变成卡通眼，和参考图不符。
    for side in (-1, 1):
        v.put(-4, 7, side * 3, 'Black')
        v.put(-5, 7, side * 3, 'White')

    # ------------------------------------------------------------ 尾巴
    # 茎要 3 格粗（只做 1 格会在渲染里断掉），再向上弯到 (9,12)；末端两片扁尾鳍向后张开成 V。
    # 两撮直立的尖角是错的形态，改成同一层横向张开才对。
    for x, y in ((6, 9), (7, 10), (8, 11), (9, 12)):
        for dz in (-1, 0, 1):
            v.put(x, y, dz, 'Blue')
        v.put(x + 1, y, 0, 'Blue')
    for dz, dx in ((-2, 0), (-3, 0), (-4, 1), (1, 0), (2, 0), (3, 1)):
        v.put(9 + dx, 13, dz, 'Blue')
        v.put(9 + dx, 14, dz, 'Blue')

    # ------------------------------------------------------------ 胸鳍
    # 从身体侧下方斜着伸出去，略微下压：直线伸出会像翅膀。
    for side in (-1, 1):
        for k in range(0, 4):
            v.put(-1 + (k // 2), 3 - (1 if k >= 2 else 0), side * (4 + k), 'Blue')

    # ------------------------------------------------------------ 棕榈树
    # 位置是这版最反直觉的一处：放在鲸身侧面（+x 侧）会被身体整个挡住，
    # 必须放到岛的右前角（x≈5, z≈4 和 x≈3, z≈6）才能从主视角看见。
    def palm(bx, bz, height):
        for h in range(1, height + 1):
            v.put(bx, h, bz, 'Reddish Brown')
        top = height + 1
        for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            v.put(bx + dx, top, bz + dz, 'Green')
        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2)):   # 叶尖下垂一格，才不是一棵灌木
            v.put(bx + dx, top, bz + dz, 'Green')
            v.put(bx + dx, top - 1, bz + dz, 'Bright Green')
        for dx, dz in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            v.put(bx + dx, top, bz + dz, 'Bright Green')
        v.put(bx, top + 1, bz, 'Green')

    palm(5, 4, 4)
    palm(3, 6, 3)

    # ------------------------------------------------------------ 小灯
    for dx in (0, 1):
        for dz in (0, 1):
            v.put(-1 + dx, 1, 4 + dz, 'Bright Light Orange')
    v.put(-1, 2, 4, 'Yellow')


def v_hash(x, y, z, salt=0):
    """坐标的确定伪随机（gen.py 里的 hash01 同一套算法）。

    场景文件被 gen.py 加载时也能直接用 hash01，这里内联一份是为了让本文件
    单独 import 也不报错。
    """
    n = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (salt * 2654435761)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0
