# 🛠️ 我的工具集 (my-toolkit)

一个基于 Flask + Docker 的个人网页工具集，用于快速整合和管理常用工具。

---

## 当前工具

- **文件整理工具** → `/tools/file-flatten`
- **Torrent 转 Magnet** → `/tools/torrent-to-magnet`

---

## 快速启动

```bash
cd my-toolkit
docker compose up --build -d
```

### 如何快速新增工具（推荐方式）

在 tools/ 目录下创建一个新文件夹，例如 tools/newtool/

在该文件夹内创建 routes.py（复制现有工具模板修改）

在 templates/ 下创建对应 HTML 页面（建议 templates/newtool/index.html）

修改 app.py，添加 Blueprint 注册：

Pythonfrom tools.newtool.routes import newtool_bp

app.register_blueprint(newtool_bp, url_prefix='/tools/newtool')

结构清晰、易扩展，欢迎持续扩充！