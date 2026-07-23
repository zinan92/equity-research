# 产业图鉴 Atlas（N5 前端 · Epic #120）

产业世界模型的产品视图：先看产业，再看公司。总览 / 产业链 / 三高气泡 / 个股全景表 / S/A/B 分级 / 公司工作台，全部 hash 深链接可寻址。

## 本地运行

```bash
# 1. 生成开发 fixture（读取爱牛归档，只需跑一次）
python3 product/static/atlas/build_fixtures.py

# 2. 启动静态服务器
python3 -m http.server 8123 -d product/static/atlas
# 打开 http://localhost:8123
```

## 数据边界（重要）

- `fixtures/` 由 `build_fixtures.py` 从 `research/ainiusq-niu/2026-07-22/data/exported/` 生成，
  是 **2026-07-02 的归档快照**，已 gitignore，**禁止进入生产构建**。
- 生产版数据源必须替换为 N2 canonical API；`js/data.js` 是唯一接缝，替换 `api` 对象即可。
- 页面所有行情/估值处均显示 as_of 与 FIXTURE 标识，不伪装实时。

## 结构

```
index.html          外壳（顶栏/搜索/底部导航）
atlas.css           铅字研究终端主题（暗色高密度，宋体标题+等宽数字，红涨绿跌）
js/main.js          hash 路由 + 全局搜索
js/data.js          数据层（fixture ↔ 未来 canonical API 的接缝）
js/util.js          DOM/格式化/迷你 Markdown（输入全转义，仅白名单标签）
js/views/home.js    总览
js/views/chains.js  22 套产业链结构 + 环节→公司跳转
js/views/bubble.js  三高气泡图（SVG）+ 环节催化剂联动
js/views/table.js   649 家个股虚拟滚动表（全列排序+多维筛选）
js/views/grades.js  661 只 S/A/B 分级表（修复爱牛表头无排序缺陷）
js/views/company.js 公司工作台（位置/评分/三高/钻取/主营/路线图/档案）
```

## 已验证（2026-07-23）

- 六条路由深链接可用；649 行虚拟滚动（滚动窗口 ≈26 行 DOM 节点）。
- 表头排序双向、筛选、搜索（代码/名称/细分/链）联动。
- 气泡点击 → 环节周期与催化剂面板；环节 → 相关公司表。
- 档案 Markdown（标题/表格/列表/引用）渲染，与母版逐字节等长。
- 375px 视口六条路由无横向溢出，底部导航生效；console 零错误。
