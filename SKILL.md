---
name: lego-3d-voxel
description: Turn a 3D subject into a buildable LEGO set one brick per voxel cell. Two routes: slice a real model (GLB/GLTF) into horizontal brick courses with colours from its own texture, or — when the reference is already blocky/voxel art and no model exists — generate the voxels procedurally with primitives. Use for "build this in LEGO, layer by layer".
---

# 3D 形体 → 逐层切片 → 积木

把用户给的 3D 模型（GLB）**真的按层切开**，每层按切片铺砖、逐层叠起来，颜色取自模型自带贴图。
这是"形体优先"的做法：件数不设上限，外形、空腔、朝向必须忠实于原作。

两条路线，按手上有什么来选：

- **有模型文件** → 切片（本文主线）。几何与颜色只能来自模型本身；不要用照片取色，
  也不要"看着渲染图想象形状"——那两条路都试过，形状失真 + 颜色全错，用户明确否决。
- **只有体素风/像素风的参考图** → 程序化生成（见「没有模型文件」一节）。几何来自图里的块面，
  颜色来自图里的色块，逐格写死、不用随机数。

## 自包含声明

本 skill **不依赖任何外部文件**：色板（15 色）、颜色归并表（材质分组）、解析器、洪泛、去噪全部内置在
`scripts/vox.py` 里，只要求 `numpy` + `pillow`。不传 `--merge` 就用内置表，不传 `--palette` 就用内置色板。

- 产出只有一个文件：`volume.json`（`{nx,ny,nz,up,front,cam,cells:[[列,层,深,色名],...]}`）。
- `scripts/build.mjs` 是装配模板（把 cells 逐格变成 `m.box`）；`scripts/preview.py` 是自带的校验渲染器，
  都不依赖外部工程。若宿主工程有 `lego.mjs` 之类的打包/检查工具链，那是**可选的下一步**，不是本 skill 的依赖。
- 换句话说：把这个目录整个拷到任何机器上，只要有 python + numpy + pillow，就能从 GLB 跑到 volume.json。

## 什么时候用

- 用户给了 `.glb` / `.gltf`（扫描件、雕刻、游戏资产），要求拼成积木、要求"一层一层切"。
- 用户给的参考图**本身就是体素/像素风**（块面清楚），要求照着拼 → 走「没有模型文件」那节。
- 写实照片、没有模型也没有现成体素块面 → 两条路都不成立，先跟用户对齐预期，不要硬做。

## 铁律（违反必然返工）

1. **不要从图片取色。** 颜色只来自模型贴图。照片取色在光照/贴图缺失下会把整件东西做成脏色。
2. **不要按列 min..max 填实。** 那是"垂直柱子"的根因，会把手下面、胳膊与身体之间的空腔填死。
   必须用三维洪泛判内外（见 `references/pipeline.md` 第 6 节）。
3. **不要让 build.mjs 做任何"智能修补"**（不补柱、不改色、不剪格子）。修补会把空心结构焊死、把细节糊平。
   几何/颜色的所有决策都在 `vox.py` 里做完，`build.mjs` 只负责 `m.box(x, y*3, z, 1, 1, 3, color)`。
4. **先用球验证链路。** 做任何人物/复杂形体之前，先跑一个 24 层、每层一色的球。
   球是凸的，看不出空腔问题，但能证明分层/坐标/叠砖/打包链路是对的。球错了就停下修管线。
5. **分辨率按原作尺寸给。** 0.9 m 高的坐像下 96 层才够；**五官要分开就得上 128 层**。
6. **层高与格宽的比例必须是真实砖的比例**：层高 = 总高 / 层数，格宽 = 层高 / 1.2（8 mm : 9.6 mm）。
   比例错了，整件东西会显得又矮又胖。
7. **改一个假设、验一次。** 几何错和颜色错要分开修，否则分不清是哪一处起的作用
   （眼睛那条就是"几何被埋 + 颜色被吃"两个根因同时存在）。修完必须凑近看像素，
   不能因为"两个参数都开了"就宣布修好——这一点我犯过。

## 流程

```bash
# 0. 依赖（只有这两个）
python -c "import numpy, PIL" || pip install numpy pillow

# 1. 切片（唯一的数据生产步骤；归并表已内置，不需要外部 json）
python <skill>/scripts/vox.py \
  --glb <model.glb> --out <work>/volume.json --courses 128

# 2. 先看三视图 + 分层图，确认朝向、比例、空腔、五官都对（这一步省不得）
python <skill>/scripts/preview.py --vol <work>/volume.json --outdir <work>

# 3. 拷 scripts/build.mjs 到工程里改路径，逐格发砖
#    再走宿主工程自己的 build / shots 检查（可选）
```

参数怎么定：

| 参数 | 默认 | 取值建议 | 说明 |
|---|---|---|---|
| `--courses` | 96 | 人像 128；小物件 64~96 | 96 层五官会糊成一块；128 层是目前的实用上限（再高只剩更贵） |
| `--merge` | `default` | `default` / `none` / 自定义 json | 内置材质归并表；`none` 看原始贴图 |
| `--absorb` | 3 | 4~6 | ≤N 格的孤立色块并进邻域主色；太大会吃掉小细节 |
| `--denoise` | 2 | 1~2 | 最后一道 3×3×3 平滑；会削 1 格宽的细线 |
| `--darkdetail` | 0.32 | 0.28~0.40 | 细黑线（闭眼/嘴缝/刻线）保底比例，见 `pipeline.md` 5b |
| `--ratio` | 1.2 | 不要改 | 格宽 = 层高 / 1.2 |

想覆盖归并表就写一份 json 传路径（键 = 目标色，数组 = 并入它的颜色）：

```json
{"Red": ["Dark Red", "Orange", "Dark Orange"],
 "Green": ["Bright Green"],
 "Bright Light Orange": ["Yellow", "Tan", "Light Nougat", "Dark Tan"]}
```

合并要按**材料**分组，不要按色相分组：肤色和红袍都很"暖"，但绝不是同一种材料。
归并的语义是"**每个区域**统一成该区域的主色"——成片的暗红阴影会保留（那是真实的明暗分区），
只有碎条纹被并掉。所以红袍变干净，但层次不丢。

## 缩放：要小一号就归并，不要降层数重切

用户说"缩小一半"指的是**成品的一半高**，也就是层数从 128 变 64。但**不要**用 `--courses 64` 重切：

| 做法 | 代价 |
|---|---|
| `--courses 64` 重切 | 重新走 2M 面 × 7 点采样 + 全量排序，峰值 1.2 GB 以上。本机页面文件被关闭（可提交内存 = 物理内存），空闲剩 1.2 GB 时连 17 MB 都分配不出来：`ArrayMemoryError` 或 OpenBLAS `Memory allocation still failed` |
| **`downscale.py` 归并** ✅ | 只读已验收的 volume.json，2 秒、几十 MB、输出确定性；`--factor 2` = 每个方向减半 |

```bash
python <skill>/scripts/downscale.py --src <work>/volume.json --out <work>_half/volume.json
python <skill>/scripts/preview.py --vol <work>_half/volume.json --outdir <work>_half --px 8 --floors 4
```

规则：**先按 128 层切细，再归并**。反过来（先切 64 层）表面更糙，而且内存一样要花。

实测（鹿 01-creature，`--factor 2`）：

| | 128 层 | 减半后 |
|---|---|---|
| 网格 | 95 × 128 × 73 | 48 × 64 × 37 |
| 体素 | 69,826 | 10,809 |
| 件数 | 22,689 | 5,055 |
| 未连接 | 74 | 39 |

**必须主动说明的损失**：1 格宽的细结构（鹿角尖、细腿、手指、衣带）归并后会变粗或断开。
归并的定色规则是"2×2×2 块里出现次数最多的颜色"，不做插值——插值会造出模型里没有的颜色。

第 2 步的验收标准（看 `view_front.png` / `view_side.png` / `layers.png`）：

- 正视图轮廓与模型一致，**不是**一根根竖直的柱子；
- 抬手臂/裙摆下方是空的，能看到背景色；
- 颜色分区合理（脸是肤色、眉眼是深色、衣袍成片），没有大面积斑驳噪点；
- **脸要凑近单独看**：眉毛 / 眼睛 / 胡子是分开的三层，眼睛不能消失。

## 没有模型文件：程序化生成体素

参考图本身就是**体素风/像素风**（块面清楚、色块分明）时，不要去找模型切片——图里已经带着
格子决策（哪里 1 格、哪里 3 格），照块面写基本形最准，还能直接控制格数与件数。

```bash
python <skill>/scripts/gen.py --scene <work>/scene.py --out <work>/volume.json
python <skill>/scripts/preview.py --vol <work>/volume.json --outdir <work> --px 8
# 再走 build.mjs 装配 + 宿主渲染，**看成品渲染图**（下面第 1 条）
```

场景文件是普通 Python 文件，只要求 `build(v)`，用基本形把格子写进去：

| 形体 | 方法 |
|---|---|
| 主体体积（身体、头） | `v.ellipsoid(cx,cy,cz,rx,ry,rz,色)` |
| 浮岛 / 树干 / 塔身（半径剖面） | `v.revolve(cx,cz,radii,top_y,色回调)`，radii 由上往下 |
| 尾巴 / 四肢 / 斜向细长体 | `v.tube(path,radius,色)`，radius=0 是逐格线 |
| 方块、眼睛、单点小件 | `v.box(...)` / `v.put(x,y,z,色)` |
| 换色不改几何（肚皮、背脊阴影） | `v.repaint(pred,色,only={'Blue'})` |
| 草皮 / 岩层杂色 | `v_hash(x,y,z,salt)` 阈值分流（确定性，可复现） |

三条实测教训：

1. **形体问题必须看 3D 渲染图。** 正视图/ASCII 图上"看着对"的形体，渲染里经常是错的：
   鲸鱼陷进草皮、棕榈被鲸身整个挡住、尾鳍成了两根短叉——三处都是正视图骗的。
2. **附件位置按主视角算，不是按坐标算。** 棕榈放在主体侧面（+x）会被身体完全挡掉，
   必须挪到岛的前角才看得见。
3. **1 格厚的斜向体在渲染里会断**（尾茎、鳍），至少给 3 格；1 格厚的悬挑（叶尖、灯笼）
   必然产生未连接，交付时一起报。

完整实战（8 版迭代、每版改了什么、被推翻的做法、必须主动说的代价）见 `references/procedural.md`；
可直接改的例子是 `examples/whale-island.py`：19 × 22 × 16 格、1,265 格 → 430 件、11 色、33 处未连接。

## 排错：先查这张表

| 症状 | 病因 | 修法 |
|---|---|---|
| 几乎全白 / 只有零星颜色 | 取色退路把 RGB 和平方放大，全被量化成 White | `tbl[:, :3].sum(0) / tot`，不要再乘样本数 |
| 每格颜色像是"对面那一侧"的 | 方向数组顺序和 `binid` 编码反了 | `NB = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]`，`binid = ax*2 + (sgn<0)` |
| 成品是一根根垂直柱子、空腔被填死 | 按列 min..max 填实 | 三维洪泛：外壳 dilate(2) 封缝 → 从边界洪泛外部空气 → `S = Ssurf \| erode(erode(~out))` |
| 只剩一层皮，内部全空 | 单层壳的三角面之间有缝，外部空气漏满内部 | 洪泛前先把壳 dilate 两圈封缝，洪泛后 erode 两圈收回 |
| 颜色整体偏 / 整片错位 | glTF 的 UV 原点在左上角，V 被额外翻转 | `ty = v * (th-1)`，**不要** `1-v` |
| 眉眼糊成一片 | 票箱取众数 / 平均 | 改成**面积加权**（`pipeline.md` 5a），再不行是层数不够 |
| **眼睛/嘴缝/刻线整个消失** | ① 凹槽被 dilate 封死→判成内部→被回填；② 细线被"面积最大"取色吃掉 | 两条都要加：反填 `carve` + `--darkdetail`（见 `pipeline.md` 5b/6b）。**注意：财神这份扫描件两处都开了仍没出来，属未解决，别照抄结论** |
| 脸上/袍上一块块杂色、"脏" | 扫描贴图是抹开的，同一材料上混着 3~4 个近似色 | `--merge default` 按区域归并 + `--absorb 6` |
| 大量零件报 not connected | 同色才并砖；异色同层不连接、下方又没砖 | 见 `pitfalls.md` 第 7 条（已知未解决） |

## 已知未解决（交付前必须自己复核，不要照抄旧结论）

1. **眼睛/细五官**：carve 与 `--darkdetail` 已实装、参数已调，但在财神 GLB 上 128 层渲染仍看不到成对的眼睛；
   192 层、关去噪均无效。查法见 `pitfalls.md` 6b 与 `scripts/probe.py --profile`。
2. **连接**：`lego build` 报 503 处 `not connected`（128 层），底部外沿换色断连。
3. **成片脏区**：帽子/袍面仍会残留少量异色成片块（如帽子上出现绿色），归并表只能治"同材料近似色"，
   治不了贴图本身串色。

这三条都属于"方法骨架对、最后一公里没跑完"。写进文档是为了下次从这里接着查，不是已完成的证据。

细节算法、参数取值、验证脚本全部在 `references/`：
- `references/pipeline.md` — 十一个步骤的完整算法与数值约定（必读）
- `references/pitfalls.md` — 每个坑的完整复盘：现象、根因、为什么当时的直觉是错的
- `references/procedural.md` — 没有模型文件时：程序化生成的基本形、8 版迭代日志、已知代价
- `references/validation.md` — 四关验收清单

脚本（全部自包含，只用 numpy + pillow）：
- `scripts/vox.py` — 切片主程序（`--ball` 出验证球）
- `scripts/gen.py` — 程序化生成：跑场景文件出 volume.json（没模型时用）
- `scripts/probe.py` — 体检：`--stats` 颜色分布 / `--layers A:B --cols C:D` 正面 ASCII 色图 / `--profile 列,层` 深度剖面
- `scripts/preview.py` — 三视图 + 分层图
- `scripts/downscale.py` — 尺寸缩放：`--factor 2` 即一半（见上文「缩放」一节）
- `scripts/build.mjs` — 装配模板（拷到 volume.json 同目录，只改 title）

排查顺序建议：`probe.py --stats` → `--layers/--cols` 看特征在不在 → `--profile` 看是不是被挡住 →
改一个参数重跑 → 再看一次。**每一步都用数据确认，不靠"参数开了就该好"。**
