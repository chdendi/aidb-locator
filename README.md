# aidb-locator

AI 驱动的 Android 调试桥 — 通过 CLI 和 MCP Server 实现 Android UI 检查与操控。

[English](README_en.md)

> 基于 [CodeLocator](https://github.com/bytedance/CodeLocator) 协议构建，无需依赖 Android Studio。Apache 2.0 协议。

## Web UI（推荐 ⭐）

最简单的使用方式：浏览器里直接看、点、改。

```bash
pip3 install git+https://github.com/chdendi/aidb-locator.git
aidb-ui                         # 启动本地服务，自动打开浏览器
```

![aidb-ui screenshot](docs/img/aidb-ui-screenshot.png)

**核心交互**

- **三栏布局**：左 view 树 + 中间设备截图 + 右属性/编辑面板，分隔条可拖动；列宽根据内容自动 fit
- **点击截图任意位置** → 自动找到对应 view（智能跳过透明 overlay 容器）
- **悬停截图** → 红虚框跟随；selected ↔ hover 之间显示 **Figma 风格距离测量**（含 margin 边沿）
- **选中节点** → 树自动展开 + 滚动到对应行；canvas 上叠加 padding（绿）+ margin（黄）半透明区
- **触控板双指捏合**缩放截图，双指滚动平移

**编辑能力（所见即所得）**

- 文字 / Padding / Margin / 透明度 / 背景色 / 文字色 / 文字大小 / 可见性 / 宽高 / 位移 / 缩放
- 颜色支持 picker + ARGB hex 双向
- **应用 / 撤销 状态机**：未改不显示按钮；改了 → 应用；apply 后 → 撤销可一键还原；占位避免布局抖动
- 应用编辑后**自动刷新且保留焦点**（按 mem_addr 在新树中找回选中节点）

**导出 / 协作**

- **📋 Copy element**：节点详情 + 完整层级链 + Activity / Fragments，markdown 格式，直接喂 AI
- **📋 copy 改动**：所有 applied 改动汇总（label · 原值 → 新值）+ element 信息
- 导出 layout JSON / 单 view 渲染截图
- 顶栏 Activity / Fragment 信息；多设备下拉切换；底栏 Schema 跳转

**启动选项**

```bash
aidb-ui --port 8888             # 指定端口
aidb-ui --no-browser            # 只起服务不开浏览器
aidb-ui --host 0.0.0.0          # 局域网共享（会打印安全警告）
```

> 没看到 view 树？右侧会有橙色提示。常见原因：装的不是 debug 包 / 当前页面不是你的 app / SDK 未集成。截图功能不依赖 SDK，仍可用。

## 它能做什么

aidb-locator 让 AI agent 具备 Android UI 调试的基础能力：

| 能力 | CLI 命令 | 说明 |
|------|----------|------|
| View 层级树 | `aidb layout` | 获取完整 View 树 + Activity/Fragment 信息 |
| View 属性编辑 | `aidb edit` | 实时修改 padding、margin、文字、可见性等 |
| 触摸定位 | `aidb touch` | 给定坐标，返回对应的 View |
| 模拟点击 | `aidb click` | 在指定坐标触发点击事件 |
| 深度链接 | `aidb schema` | 发送 Schema URL 跳转页面 |
| 文件浏览 | `aidb files` | 获取应用文件系统目录树 |
| 文件操作 | `aidb file-op` | 复制、移动、删除应用内文件 |
| View 截图 | `aidb capture` | 获取单个 View 的渲染截图 |
| 数据读取 | `aidb view-data` | 获取 View 绑定的数据 |
| 数据设置 | `aidb view-data --set` | 设置 View 上的数据 |

## 安装

```bash
pip3 install git+https://github.com/chdendi/aidb-locator.git
```

> **注意：** 请使用 `pip3`，不要使用 `pip`。`pip` 可能指向 Python 2.7，不支持 `pyproject.toml` 构建。

### 前置条件

- Android 设备已集成 CodeLocator SDK（debug 包）
- 系统 PATH 中包含 `adb`

## CLI 使用

```bash
# 设备管理
aidb devices                            # 列出已连接设备

# UI 检查
aidb layout                             # 查看 View 层级树
aidb layout --json                      # JSON 格式输出
aidb activity                           # 查看当前 Activity + Fragment
aidb touch 540 960                      # 定位坐标 (540, 960) 的 View

# UI 操控
aidb click 540 960                      # 模拟点击
aidb edit <view_addr> T "新文字"         # 修改 View 文字
aidb edit <view_addr> P "16,8,16,8"     # 修改 padding
aidb edit <view_addr> A "0.5"           # 修改透明度

# 导航
aidb schema "myapp://home"              # 发送深度链接

# 文件
aidb files                              # 浏览应用文件
aidb file-op <source> <target> copy     # 文件操作

# 截图 & 数据
aidb capture <view_addr> -o shot.png    # View 截图
aidb view-data <view_addr>              # 获取 View 数据
aidb view-data <view_addr> --set "data" # 设置 View 数据
```

### 全局选项

| 选项 | 说明 |
|------|------|
| `--device`, `-d` | 指定设备序列号（多设备场景） |
| `--json` | 以 JSON 格式输出 |

### EditType 速查表

| 代码 | 属性 | 示例 |
|------|------|------|
| `T` | 文字 | `aidb edit <addr> T "Hello"` |
| `P` | Padding | `aidb edit <addr> P "16,8,16,8"` |
| `M` | Margin | `aidb edit <addr> M "0,16,0,16"` |
| `A` | 透明度 | `aidb edit <addr> A "0.5"` |
| `B` | 背景色 | `aidb edit <addr> B "#FF0000"` |
| `TC` | 文字颜色 | `aidb edit <addr> TC "#333333"` |
| `TS` | 文字大小 | `aidb edit <addr> TS "16"` |
| `VF` | 可见性 | `aidb edit <addr> VF "V/I/G"` |
| `LP` | 宽高 | `aidb edit <addr> LP "200,100"` |
| `TXY` | 位移 | `aidb edit <addr> TXY "10,20"` |
| `SCXY` | 缩放 | `aidb edit <addr> SCXY "1.5,1.5"` |

## MCP Server

启动 MCP Server，让 AI agent 直接调用：

```bash
aidb serve
```

### 配置到 Claude Code / Cursor

```json
{
  "mcpServers": {
    "aidb-locator": {
      "command": "aidb",
      "args": ["serve"]
    }
  }
}
```

### 可用的 MCP Tools

| Tool | 说明 |
|------|------|
| `aidb_grab_layout` | 获取 View 层级树 + Activity/Fragment |
| `aidb_edit_view` | 编辑 View 属性 |
| `aidb_get_touch_view` | 坐标定位 View |
| `aidb_mock_touch` | 模拟点击 |
| `aidb_send_schema` | 发送深度链接 |
| `aidb_list_files` | 文件目录树 |
| `aidb_operate_file` | 文件操作 |
| `aidb_capture_view` | View 截图（返回 PNG 图片） |
| `aidb_get_view_data` | 获取 View 数据 |
| `aidb_set_view_data` | 设置 View 数据 |

## 架构

```
aidb_locator/
├── adb.py          # ADB 通信层（subprocess 封装）
├── protocol.py     # CodeLocator 协议（编码/解码/常量）
├── models.py       # 数据模型（上游 JSON 字段映射）
├── commands.py     # 10 项能力的高层 API
├── cli.py          # Click CLI
└── mcp_server.py   # MCP Server
```

依赖方向：`cli / mcp_server → commands → protocol → adb`

## 工作原理

aidb-locator 是 CodeLocator 协议的独立客户端，通过标准 ADB broadcast 与设备端 SDK 通信：

```
CLI / MCP Server
    ↓ 调用
CodeLocator (commands.py)
    ↓ 编码参数
Protocol (protocol.py)
    ↓ 发送 broadcast
ADB Client (adb.py)
    ↓ adb shell am broadcast
设备端 CodeLocator SDK
    ↓ 返回结果
JSON 解析 → 结构化输出
```

无需 Android Studio，任何能执行 `adb` 的环境都能使用。

## 开发

```bash
git clone https://github.com/chdendi/aidb-locator.git
cd aidb-locator
pip install -e .
pytest tests/ -v
```

## License

Apache 2.0 — 详见 [LICENSE](LICENSE)。

本项目是 [CodeLocator](https://github.com/bytedance/CodeLocator) 协议的 CLI/MCP 客户端，CodeLocator 由 ByteDance 开发。
