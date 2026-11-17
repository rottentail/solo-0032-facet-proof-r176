# 数值计算对照资料 · Facet Proof

一套固定的对照材料，比较当前渲染实现（`facet-raster-1`，下称“服务”）与一份
研究变体在三种情形下的表现：**细件边缘混色**、**近共面部件归属**、
**透视裁剪**；另附一个**键序归属**伴随场景。

材料的用途是帮维护者分辨两件常被混为一谈的事：

- **颜色近似** —— RGB 通道接近或变化；
- **归属相同** —— `object.u32` 通道指向同一个冻结部件键。

同时也讲清两种不同的复核动作各自的证明力：**重新读取旧图版**只证明字节自洽
与未被替换；**用旧输入重新渲染**证明这些字节确实由某份实现从某份输入产出。
二者都不能单独证明几何正确，几何结论来自资料内独立的射线投射 oracle。

## 目录

```
evidence/numeric-variant-comparison/
├── README.md                 本文件：如何看、如何用
├── notes/reading-guide.md    详细判读说明（通道语义、每格图例、局限）
├── scenarios/*.json          场景定义（网格、材质、镜头、探针）
├── harness/                  构建与复核脚本（运行副本）
│   ├── build.py              生成一套新的固定资料
│   ├── verify.py             只读固定目录复核
│   ├── drift.py              报告工作树与固定副本的差异
│   ├── variant.py            研究变体（不导入服务渲染器）
│   ├── oracle.py             独立射线投射 oracle
│   ├── job.py                冻结输入与基线重放
│   ├── compare.py            通道比较与自洽检查
│   ├── scenario.py, keyorder.py, sheet.py, pngdiff.py, font.py
└── artifacts/<build-id>/     固定产物（每次构建一个新目录）
```

## 如何看一套固定产物

先读 `artifacts/<build-id>/manifest.json`：

- `build_digest`：整套记录（含随机标识）的摘要；
- `content_digest`：可复现内容的摘要，跨构建稳定；
- `support` / `offline_reader`：构建时使用的脚本与模块摘要；
- `scenarios.<name>.input_digest`：该场景“画出这张图所需的最小输入”摘要；
- `scenarios.<name>.service_plate.pass_sha256`：服务产出的六个通道摘要。

然后按场景看 `sheets/` 下两张自带标签的 PNG：

1. `<scenario>-01-color-and-ownership.png` —— 服务颜色、研究颜色、归属变化图、
   颜色差异图，以及探针窗口的整数放大；
2. `<scenario>-02-attribution.png` —— 每个诊断分支单独回退一项后的归属变化图，
   用来确认差异究竟来自哪一项。

每张图都把标题、输入摘要、服务图版摘要、逐通道计数直接印在图上，单独拷走
也不会丢失含义。数值细节在 `readings/<scenario>.json`。

## 本目录已固定的那一套

`artifacts/build-2026-11-16/` 是当前随仓库提交的一套：

- `content_digest` `9ba0fb36927850fa41b3dab67e54303416941274ec45aa1dc20ddf09e024caa7`
  ——只覆盖可复现内容（代码摘要、冻结输入、通道字节、对照图、计数），
  两次构建相同代码与输入会得到同一个值；
- `build_digest` `a02624daa86db377a9a0052e140482a858fb9513ea2a70ff8cf0f65d51d4be60`
  ——额外包含服务随机分配的图版/密封标识，因此每次构建都不同，这是预期行为；
- 服务渲染器 `facet-raster-1`，构建时 `drift.py` 报告工作树与固定副本一致

| 场景 | `input_digest` 前缀 | 服务图版 `visual_hash` 前缀 |
| --- | --- | --- |
| edge-blend | `80d3a7e7434958d3` | `2f8c775097b97083` |
| coplanar-ownership | `929222e1d0d85d43` | `b8f0d5c847e0fcaa` |
| perspective-clipping | `4848ae9802a67365` | `4e49e749aa3895ab` |

这些前缀只用于人工核对整套材料是否对得上；权威值在 `manifest.json`。判断
“两次构建是否等价的证据”请看 `content_digest`，不要看 `build_digest`。

## 三句话结论（对应到具体读数）

| 场景 | 研究变体相对服务 | 该看哪一格 |
| --- | --- | --- |
| 边缘混色 | 颜色 205 px 变化，**归属 0**，深度 0 位 | 第 3 格全暗 = 只有颜色近似 |
| 近共面归属 | 归属 252 px（`2->1`），另有 178 px 纯颜色 | 第 3 格黄色 = 归属真的变了 |
| 透视裁剪 | 深度 3311 位，归属 21 px（`1->3`），覆盖不变 | 第 3、4 格同时有信号 |
| 键序（伴随） | 归属 340 px（`2->1`），颜色 0 px 超容差，深度 0 位 | 服务 `/comparisons` 完全不报归属 |

`readings/key-order.json` 还记录了服务 `POST /comparisons` 的原始返回：
它只有颜色、轮廓、深度字段，**没有对象通道字段**。所以“比对结果无差异”不能
推出“归属相同”。

## 复核与重建

```sh
# 复核：只读固定目录内的副本，不加载工作树
python3 -I evidence/numeric-variant-comparison/harness/verify.py \
    evidence/numeric-variant-comparison/artifacts/<build-id>
# 退出 0 = 所有摘要、重放、离线包校验通过；2 = 有差异

# 漂移：工作树是否已偏离固定副本（不修改任何固定材料）
python3 -I evidence/numeric-variant-comparison/harness/drift.py \
    evidence/numeric-variant-comparison/artifacts/<build-id>

# 新建一套资料（新目录，绝不覆盖）
python3 -I evidence/numeric-variant-comparison/harness/build.py \
    --output evidence/numeric-variant-comparison/artifacts/<new-build-id>
```

固定目录一旦生成，就不再由脚本改写。脚本后续变化会体现在 `drift.py` 的差异
列表中，但旧图版、旧通道和旧判读数字保持原义。需要新结论时新建一套，而不是
在旧目录上“更新”。

## 边界

- 平局窗口内的像素由策略决定；oracle 明确弃权并计入 `ambiguous_pixels`。
- 资料只覆盖透视镜头；研究变体也不处理瓦片续算、租约和取消。
- 研究变体是研究对照实现，不是候选发布版本。
- 所有图像均为整数最近邻放大，图内已注明；未做任何会改变像素含义的平滑。

更完整的判读规则、平局处理与已知局限见 `notes/reading-guide.md`。

## 工具与记录的关系

`support/` 里固定三类内容，用途不同：

- `support/harness/`：产生图版与读数的模块（变体、冻结作业、oracle、比较、
  绘图）。它们参与 `content_digest`，因为改动会改变证据。
- `support/facetproof/`、`support/facetreader/`：服务渲染器与独立读取器副本。
  同样参与 `content_digest`。
- `support/tools/`：`build.py`、`verify.py`、`drift.py` 的构建时副本。它们记录
  “这份资料是怎么产生的”，但**不参与** `content_digest`，因为工具可以在两次
  等价构建之间演进。`drift.py` 会单独报告它们的差异，并标出 `scope`。

复核旧材料的正确入口始终是 `verify.py`（只读目录内副本、只做重放与摘要核对），
不是重跑当前 `build.py`。
