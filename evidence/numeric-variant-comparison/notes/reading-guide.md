# 数值对照资料 · 判读说明

这套资料回答的问题只有一个：同一份冻结输入下，**当前实现**（服务基线，
`facet-raster-1`）与**一份研究变体**在三种容易混淆的情形中各做了什么，以及
图上的差异应当归到哪个通道。

材料固定在 `artifacts/<build-id>/` 里。目录内的 `support/` 是构建时使用的
脚本与渲染器副本，`inputs/` 是该次渲染真正消费的冻结输入，`plates/` 是服务
自己产出的通道字节。**之后的脚本改动不会改变这些图版的含义**，只会让
`harness/drift.py` 报告与钉住副本的差异。

## 一、先分清三件事

阅读任何一张对照图之前，先把下面三件事分开。它们常被混为一谈。

1. **颜色近似**：RGB 通道在某个像素上接近或发生变化。它说明参与该像素的
   光照、材质、采样组合发生了变化。
2. **归属相同**：`object.u32` 通道在某个像素上指向同一个冻结部件键。它说明
   维护者应当把该像素算作哪个零件。
3. **深度一致**：`depth.f32` 通道在某个像素上给出相同的相机前向距离。它说明
   可见表面的前后关系。

服务端图版把三者分别存成独立通道，而且**下采样规则并不相同**：深度与物体
编号取最近的那个超采样点，颜色却对全部超采样点取线性平均。因此边缘像素上
颜色变了、归属没变，是设计使然而不是矛盾。资料里每张图都把颜色差异图
（第 4 格）与归属差异图（第 3 格）并排放，就是为了不让读者用一张图去回答另一
个问题。

## 二、材料构成

`artifacts/<build-id>/` 下：

| 路径 | 内容 | 绑定方式 |
| --- | --- | --- |
| `manifest.json` | 构建摘要、`content_digest`、每个文件的 SHA-256、支撑代码摘要 | 自身摘要 |
| `support/harness/` | 变体与判读脚本副本 | 摘要写入 manifest，参与 `content_digest` |
| `support/facetproof/` | 服务渲染模块副本 | 摘要写入 manifest，参与 `content_digest` |
| `support/facetreader/` | 独立离线读取器副本 | 摘要写入 manifest，参与 `content_digest` |
| `support/tools/` | 构建与复核脚本副本（`build.py`、`verify.py`、`drift.py`） | 摘要写入 manifest，**不**参与 `content_digest` |
| `inputs/<scenario>.json` | 渲染真正消费的冻结输入（不含数据库标识） | `input_digest` |
| `plates/<scenario>/service-*` | 服务产出的六个通道 | 每通道 SHA-256 |
| `plates/<scenario>/research-*` | 研究变体产出的六个通道 | 由固定输入重放 |
| `sheets/*.png` | 自带标签的对照图 | 摘要写入 manifest |
| `readings/<scenario>.json` | 通道读数、oracle 结果、各诊断分支计数 | 摘要写入 manifest |
| `readings/key-order*.json` | 键序对照的部件映射与通道读数 | 摘要写入 manifest |
| `bundles/<scenario>.zip` | 服务导出的离线包 | 可由独立读取器复核 |

`inputs/` 只保留决定输出的值：镜头、光照、各部件矩阵、网格与材质、请求尺寸
与采样数。图版 id、曝光 id、网格 id 这类标识不在其中，因此 `input_digest`
描述的是“画出这张图所需的最小输入”，而不是数据库行。

## 三、三种情形与各自证据

### 1. 边缘混色（`edge-blend`）

细条只覆盖像素内部分超采样点。baseline 对这些点取平均颜色，物体编号取最近
那个点，两者本来就会不一致。

- 服务：颜色有 205 个像素的过渡带。
- 研究变体：边缘颜色改成“取最近超采样点的颜色”。颜色变化 **205 px，全部
  为 color-only**；归属变化 0；深度位变化 0。
- 判读：这类差异是**颜色近似**，不是归属变化。看第 3 格（全暗）即可确认。
- 证据位置：`sheets/edge-blend-01-color-and-ownership.png`，
  第 5、6 格是同一探针窗口的整数放大，用于看清单个像素的过渡。

### 2. 近共面归属（`coplanar-ownership`）

两块面片深度相差 1e-9，远小于服务端 1e-9 的平局窗口之外的量级。

- 服务：编号 2 的部件在重叠区可见（`ownership_transitions` 为空是基线）。
- 研究变体：平局窗口放宽到 4e-9 后，**252 个像素从编号 2 改归编号 1**。
  颜色在这 252 个像素上同时变化（两边材质不同），另有 178 px 是纯颜色变化。
- 关键点：这里既有颜色差异也有归属差异。只报告“颜色变了 430 px”会掩盖
  归属移动；只报告“归属变了 252 px”会漏掉纯颜色部分。两份材料都在
  `readings/coplanar-ownership.json` 的 `against_service` 里。
- oracle：射线投射在 5988 px 上独立复核归属与深度全部一致；另有 256 px 被
  标为 ambiguous——两点距离在 1e-7 以内，几何本身无法裁决，需要平局策略。
  这 256 px **不应**被算作任何一方的错误。
- 证据位置：`sheets/coplanar-ownership-01-*.png`、`-02-attribution.png`。

### 3. 透视裁剪（`perspective-clipping`）

刀片三角形穿过近裁剪面，必须被裁剪成新的多边形。

- 服务：裁剪后按透视正确插值深度，oracle 在 6799 px 上全部一致。
- 研究变体把透视深度插值换成屏幕空间线性插值（一个常见错误）：
  **3311 px 深度位发生变化**，最大差 1.596，均值 0.644；其中 **21 px 发生归属
  变化**（1→3），因为错误深度把前后关系排反了。独立 oracle 在这份研究图版上
  **判定不一致**：至少 17 px 归属错误、32 px 深度错误（`readings` 中的列表
  各截断到 32 条，`ownership_mismatch_count` / `depth_mismatch_count` 才是
  完整计数）。
- 只回退这一个开关（`perspective-depth` 分支）时，深度与归属完全恢复，只剩
  131 px 边缘颜色差。这说明 21 px 归属变化确实来自深度插值，而不是裁剪顺序
  或光栅化舍入。
- `reject-near-faces` 分支演示另一种失败：整面丢弃造成 2066 px 覆盖丢失。
  覆盖丢失也体现在归属通道上（1→0），与颜色无关。
- 证据位置：`sheets/perspective-clipping-01-*.png`、`-02-attribution.png`。

### 伴随场景 4. 键序归属（`key-order`）

同一网格、同一材质、同一镜头，只交换两个部件的放置键。基线按排序后的键编号
对象，于是：

- 颜色：服务自带的比对按容差 2 报告 `color_changed 0`；逐字节比较只有 4 px
  变化（`mean_channel_delta` 约 0.0023，来自边缘平均的极小差）。
- 深度：0 位变化。
- 归属：**340 px 换了主人**（`2->1` 全部 340 px；其中 336 px 颜色完全不变，
  4 px 颜色与归属同时变化）。
- 服务的 `POST /comparisons` 报告 `color_changed 0, depth_changed 0,
  silhouette_changed 0`，**它根本不读对象通道**，因此不会提到归属变化。

这条场景不是某个构建的缺陷，而是说明“两个图版看起来一样”与“两个图版把
同一个像素算给同一个零件”是两回事。证据位置：
`sheets/key-order-01-ownership-without-geometry-change.png`。

## 四、两种“再看一遍”能说明什么

材料刻意把两种动作分开保存，因为它们的证明力不同。

### A. 重新读取旧图版（`bundles/*.zip`，用 `facetreader`）

读取的对象是**当时已经产出的字节**。

能说明：

- 包内六个通道、元数据和来源声明彼此一致；
- 图版引用的冻结密封摘要、镜头摘要、对象映射与包内副本相符；
- 颜色 PNG 与原始 RGB 通道逐字节相同，物体预览符合公开公式。

不能说明：

- 这些字节确实是当前服务生成的（包内摘要可被整体替换）；
- 当前服务中的审阅意见仍然有效（ZIP 不含审阅或隔离状态）；
- 图像在几何上正确（读取器只交叉核对通道，不重新渲染）。

用途：确认“旧图版作为历史记录没有被篡改”以及“交付包自洽”。

### B. 用旧输入重新渲染（`inputs/*.json` + 固定渲染器副本）

输入是冻结的最小渲染输入，渲染器是 `support/facetproof/` 的副本。

能说明：

- 在**该副本**下，同一输入逐字节复现同一个图版（`verify.py` 每次构建都会
  断言这一点）；
- 服务图版确实来自这份输入和这份代码，而不是后来的重命名或替换；
- 研究变体与基线在同一输入上的差异可以逐通道归因。

不能说明：

- 当前工作树的渲染器仍会产出相同结果——这需要重跑并比对 `manifest` 摘要；
- 平局像素的归属选择在别的数值后端下也相同（`coplanar-ownership` 正好
  说明它会变）。

用途：把图版钉在“实现 + 输入”上，让结论不随脚本漂移。

一句话：**读旧图版证明字节一致；重渲证明字节由谁产出。** 两者都不能单独
证明几何正确；几何结论来自第三节的独立 oracle 与逐分支对照。

## 五、研究变体改了什么

`support/harness/variant.py` 是独立实现，不导入服务渲染器，只消费冻结作业。
它与基线的差异都在模块头部逐条列出，而且每一条都能单独回退，用于归因：

1. `edge_color`: 下采样颜色取最近点而非平均（影响颜色，不影响归属）。
2. `tie_window`: 平局窗口 4e-9 而非 1e-9（影响近共面归属）。
3. `depth_interp`: 屏幕空间线性深度而非透视正确插值（影响深度，进而影响归属）。
4. `near_crossing`: 诊断分支，整面丢弃而非裁剪（影响覆盖与归属）。
5. `edge_eval`、`bary`: 纯舍入差异，用于证明这些改动在本资料场景中是惰性的。

全部开关置回基线值时，变体模块逐字节复现服务通道（构建时断言，`verify.py`
再次断言）。

## 六、如何复核与更新

```sh
# 复核钉住目录：只读目录内副本，不加载工作树
python3 -I evidence/numeric-variant-comparison/harness/verify.py \
    evidence/numeric-variant-comparison/artifacts/<build-id>

# 查看工作树是否已偏离钉住副本
python3 -I evidence/numeric-variant-comparison/harness/drift.py \
    evidence/numeric-variant-comparison/artifacts/<build-id>

# 产生一套新资料（新目录，不覆盖旧目录）
python3 -I evidence/numeric-variant-comparison/harness/build.py \
    --output evidence/numeric-variant-comparison/artifacts/<new-build-id>
```

`verify.py` 有效时退出 0，发现摘要或重放不一致时退出 2。`drift.py` 在无差异
时退出 0，有差异时退出 1，并逐项列出模块与新旧摘要；**它不会修改任何钉住
材料**。

`build_digest` 包含服务随机分配的图版与密封标识，因此每次构建都不同。
比较两次构建是否等价请看 `content_digest`：它只覆盖代码摘要、冻结输入、服务
与研究通道字节、对照图字节以及逐通道计数。注意 `readings/*.json` 里保留的是
原始服务标识，所以该文件本身的字节摘要会随构建变化；判读数字不受影响。

## 七、已知局限

- 平局窗口内的像素由策略决定，oracle 明确弃权（标为 ambiguous），不给出
  “正确归属”。
- 仅覆盖透视镜头。正交镜头不在本资料范围内。
- 研究变体是研究用途的对照实现，不是候选发布版本；它不处理瓦片续算、租约
  或取消，这些由服务基线负责。
- `edge-blend` 的细条宽度与采样数绑定；改动 `samples` 需要重新构建，并会得到
  新的 `input_digest`。
