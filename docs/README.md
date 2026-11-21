# 冰箱管家 FridgeManager

记录冰箱里的食材和保质期，并根据食谱库推荐现在能做的菜。

技术栈：Python + FastAPI + SQLite（标准库 `sqlite3`），前端是原生 HTML/CSS/JS，不需要构建。

## 目录结构

```
FridgeManager/
├─ config/
│  └─ config.json        # 所有配置（端口、数据库路径、日志路径等）
├─ docs/
│  ├─ README.md          # 本文档
│  └─ RELEASE_NOTES.md   # 更新日志（含版本号规则）
├─ VERSION               # 当前版本号，如 1.26.11.0
├─ src/
│  ├─ server.py          # 服务器入口：python -m server（Windows 服务用这个）
│  ├─ run.py             # 开发时的启动入口（PyCharm 直接运行），内部调用 server.py
│  ├─ setup_venv.bat     # 新建 venv_{版本}_{时间} 并安装全部依赖
│  ├─ config.py          # 读取配置、初始化日志、清理旧日志
│  ├─ main.py            # FastAPI 应用：接口 + 推荐逻辑
│  ├─ importer.py        # 从网页链接识别食谱
│  ├─ bump_version.py    # 发布新版本：更新 VERSION 和更新日志
│  ├─ data/recipes.json  # 种子食谱（首次运行时导入数据库）
│  └─ static/            # 前端页面
├─ venv_{版本}_{时间}/    # setup_venv.bat 生成的虚拟环境（不提交）
├─ logs/                 # 日志（自动创建）
└─ pyproject.toml        # 项目信息与依赖
```

数据库位置由 `config/config.json` 的 `database.path` 决定（可以放在项目外，例如 `D:\data\FridgeManager\fridge.db`）。

## 安装

双击 `src\setup_venv.bat`，或在命令行运行：

```powershell
src\setup_venv.bat
```

它会：
1. 用 `py -3`（没有就用 `python`）创建新的虚拟环境 `venv_{版本}_{日期时间}`，例如 `venv_1.26.11.0_20261121_180244`；
2. 升级 pip，按 `pyproject.toml` 安装全部依赖；
3. 检查依赖能否正常导入，最后打印运行命令。

想用指定的 Python：`src\setup_venv.bat "C:\Path\to\python.exe"`。在脚本里调用、不想最后暂停：先 `set NO_PAUSE=1`。

每次升级都建一个新环境，旧环境留着。新版本有问题时，把服务指回旧环境即可回退。

## 运行

```powershell
cd src
..\venv_1.26.11.0_20261121_180244\Scripts\python.exe -m server
```

然后打开 `http://127.0.0.1:{端口}`（端口见 `config.json` 的 `server.port`），接口文档在 `/docs`。临时换端口：`-m server --port 8080`。

开发时在 PyCharm 里直接运行 `src/run.py` 也可以，和 `-m server` 是同一套启动逻辑。

## 部署为 Windows 服务

用 pywin32（已包含在依赖里）注册成 Windows 服务，不需要其他工具。以**管理员身份**打开 PowerShell：

```powershell
cd D:\Code\FridgeManager\src
$PY = "..\venv_1.26.11.0_20261121_180244\Scripts\python.exe"   # 换成实际的环境目录

& $PY -m server install    # 注册服务（开机自动启动，崩溃后自动重启）
& $PY -m server start      # 启动
& $PY -m server status     # 查看状态（不需要管理员）
& $PY -m server stop       # 停止
& $PY -m server restart    # 重启
& $PY -m server remove     # 删除服务
```

服务名为 `FridgeManager`，在"服务"管理器（`services.msc`）里显示为"冰箱管家 FridgeManager"。

要点：
- **服务实际运行的命令**：`<Python 安装目录>\python.exe -S "<src>\server.py" --service --venv "<虚拟环境>"`。没有用 pywin32 默认的 `pythonservice.exe`，也没有用虚拟环境里的 `python.exe`，因为这两种方式在虚拟环境下作为服务很容易启动失败（错误 1053）。改为由真正的 Python 解释器启动，再手动加载虚拟环境里的依赖，效果和在虚拟环境中运行一样。`install` 结束时会打印完整命令。
- **自动重启**：`install` 会同时配置恢复策略：崩溃或启动失败后，依次在 5 秒、10 秒、60 秒后自动重启，一天后重置计数。
- **日志**：运行日志照常写入 `logs/fridgemanager.log`。服务的启动、停止和启动失败也会写入 Windows 事件查看器（Windows 日志 → 应用程序，来源为 FridgeManager）。
- **运行账户**：服务以 LocalSystem 身份运行，要能访问数据库所在目录（如 `D:\data\FridgeManager`）和 Python 安装目录。LocalSystem 默认都能访问。
- **防火墙**：`server.host` 为 `0.0.0.0` 时，要让局域网访问，需要放行端口（改成你的实际端口）：
  ```powershell
  New-NetFirewallRule -DisplayName "FridgeManager" -Direction Inbound -Protocol TCP -LocalPort 7922 -Action Allow
  ```
- 不是以管理员身份运行时，`install`、`start`、`stop`、`remove` 会提示"权限不足"。

**升级到新版本**（管理员 PowerShell）：

```powershell
D:\Code\FridgeManager\src\setup_venv.bat                    # 1. 建新环境 venv_<新版本>_<时间>
cd D:\Code\FridgeManager\src
& ..\venv_<新>\Scripts\python.exe -m server install         # 2. 服务已存在 → 改为使用新环境
& ..\venv_<新>\Scripts\python.exe -m server restart         # 3. 重启生效
```

回退：用旧环境的 python 执行 `-m server install` 和 `-m server restart` 即可。

## 版本

版本号规则为 `1.{年份后两位}.{月份}.{当月序号}`，当月第一个版本序号为 0，例如 `1.26.11.0`、`1.26.11.1`。版本号保存在根目录 `VERSION` 文件，网页底部会显示当前版本，更新内容见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

发布新版本：

```powershell
.venv\Scripts\python.exe src\bump_version.py --dry-run   # 先看看下一个版本号
.venv\Scripts\python.exe src\bump_version.py             # 写入 VERSION，并在更新日志顶部插入新版本标题
```

## 配置 `config/config.json`

| 键 | 说明 | 默认 |
|---|---|---|
| `server.host` / `server.port` | 监听地址 / 端口 | `127.0.0.1` / `8000` |
| `database.path` | SQLite 文件路径 | `data/fridge.db` |
| `log.path` | 日志文件路径 | `logs/fridgemanager.log` |
| `log.level` | 日志级别 | `INFO` |
| `log.retention_days` | 日志保留天数 | `14` |
| `fridge.expiring_days` | 剩余天数 ≤ 该值算"即将过期" | `3` |
| `recipe_type.meat_words` | 荤菜关键字 | 肉、鸡、鱼、虾、海参等 |
| `recipe_type.veg_exceptions` | 例外词：含这些词的食材不算荤 | 鸡蛋、牛奶、鸡毛菜等 |
| `recipe_import.allowed_hosts` | 允许导入的网站域名（必须 https） | `pullit.up.railway.app` |
| `recipe_import.seasoning_words` | 导入时默认归为"调料"的食材名（需完全相同） | 盐、油、生抽、姜片、葱花等 |
| `recipe_import.skip_words` | 导入时默认标为"删除"的食材名 | 水、清水、开水等 |
| `food_presets` | 食材预设：`name` 名称、`category` 分类、`shelf_days` 冷藏保质天数、`quantity` 默认数量（见底 / 1份～10份 / 很多） | 包菜、茄子、白菜、蘑菇、豆角、豆芽菜 |

相对路径都相对于项目根目录。也可以用环境变量 `FRIDGEMANAGER_CONFIG` 指定另一个配置文件。

## 日志

- 同时输出到控制台和 `log.path`。内容包括：启动/停止、每个 `/api` 请求（方法、路径、状态码、耗时）、食材和食谱的增删改、推荐结果数量、未捕获的异常堆栈。
- 每天午夜轮转一次，旧文件命名为 `fridgemanager.log.YYYY-MM-DD`。
- 超过 `retention_days`（默认 14 天）的旧日志会自动删除：轮转时会清理，程序启动时也会再检查一次（防止午夜时程序没在运行）。

## 功能

### 我的冰箱
- 添加、编辑、删除食材，记录名称、数量、分类、放入日期、保质期、备注。提供 +3/7/14/30 天的快捷按钮。
- 每个食材有四个按钮：**编辑**；**见底**（数量改为见底，补货清单页会提醒）；**吃完**（从冰箱移除，自动加入补货清单）；**删除**（直接删掉，不进补货清单，会二次确认）。
- 数量从下拉中选：缺货、见底、1份～10份、很多（默认 1份）。选"缺货"= 加入补货清单，不需要保质期，不在食材页显示。列表里"见底"标橙色、"很多"标绿色。以前手动填的数量（如"3 个"）编辑时会显示为"（旧）"选项，可以保留或改成新选项。
- 名称输入框带下拉列表：点一下就会列出食谱库里用到的所有食材（主料在前、调料在后，按用到的菜数排序，冰箱里已有的会标"已有"）。输入文字会筛选出名字里**包含**这些字的食材，比如输入"牛"会列出牛肉、牛腩、牛里脊。选中的食材如果在预设里，会自动填好分类、数量和保质期。支持 ↑↓ 选择、回车确认、Esc 关闭；列表里没有的名字也可以直接输入保存。
- "常用"预设按钮：点一下自动填好名称、分类、数量和保质期（放入日期 + `shelf_days`）。预设在 `config/config.json` 的 `food_presets` 里增删。
- 列表主要显示**存入日期**（如"11/16 5天前"）；只有快过期或已经过期的食材才显示到期日期，已过期标红，3 天内过期标橙。顶部显示各状态的数量。
- 排序：已过期和快过期的排在最前（按到期日），其余按存入日期从早到晚排（先放进去的先吃）。
- 保质期可以不填：勾选"不设保质期"即可（适合米、面、调料、冻品等）。这类食材显示为"不限期"，永远不会被判为过期，推荐时照常可用。
- 支持搜索、按**种类**筛选（下拉框里显示每个种类有几样）、按状态筛选（含"未设保质期"）。

### 推荐食谱
- 用冰箱里**没过期**的食材去匹配食谱库里每道菜的"主要食材"。调料默认家里都有，不参与匹配。
- 匹配比较宽松：名称互相包含就算匹配（比如"土鸡蛋"能匹配"鸡蛋"）。
- 排序：缺的食材越少越靠前 → 能用掉的临期食材越多越靠前 → 匹配率越高越靠前。
- 可以选择"最多缺少 0/1/2/不限 种食材"。选 0/1/2 时，至少要有一种食材在冰箱里才会列出来；选"不限"会显示全部食谱，即使冰箱里一样都没有。
- **今日一荤一素**：顶部分别给出排名第一的荤菜和素菜，各自可以"换一换"，下面列出两道菜还需要买的食材。
- 全部推荐列表可以按 全部 / 荤菜 / 素菜 筛选。

### 食谱库
- 内置 28 道家常菜（荤 13、素 15），可以自己添加或删除。点击卡片查看食材、调料和步骤。
- **编辑食谱**：点卡片上的"编辑"，或者打开详情后点"编辑"，会打开和导入时一样的编辑页。可以改菜名、用时、荤/素（选"自动判断"会按主料重新判断）、步骤；食材可以改名、改用量、在主料/调料/删除之间切换，也可以添加新食材。"全部恢复"会回到打开编辑页时的状态。
- 每道菜都标了荤/素。添加食谱时可以手动选，不选就按食材自动判断，添加成功的提示里会显示判断理由。点卡片上的"荤/素"标签可以切换。
- 自动判断规则（只看主要食材，不看调料）：
  1. 食材名包含 `veg_exceptions` 里的词（鸡蛋、牛奶、牛油果、鸭梨、鸡毛菜、鱼腥草、牛肝菌…）→ 跳过这个食材；
  2. 否则包含 `meat_words` 里的词（肉、鸡、鱼、虾、海参、鸽、兔、蛙、螺…）→ 整道菜判为荤；
  3. 所有食材都没命中 → 素。

  两个词表在 `config/config.json` 的 `recipe_type` 里，遇到判错的食材往里加词即可，重启生效。
- **从链接导入**：粘贴菜谱网页链接，点"识别食材"，会打开编辑页：
  - 自动识别菜名、用时、食材（含用量）和步骤。
  - 每个食材可以切换为 **主料**（参与推荐匹配）/ **调料**（默认家里有）/ **删除**。网页上"调味"分组的食材，以及 `seasoning_words` 里的常见调料，默认归为调料；`skip_words` 里的（如清水）默认删除。
  - "删除全部调料"一键去掉所有调料，"全部恢复"回到识别时的状态；食材名和用量都能直接改，比如把"鲜菌菇"改成"蘑菇"，方便和冰箱里的食材对上。
  - 保存后，详情里会显示用量和"查看原菜谱"链接。
  - **只允许从 `https://pullit.up.railway.app` 导入**，其他网站的链接会被拒绝（包括跳转到其他网站的情况）。允许的网站在 `config/config.json` 的 `recipe_import.allowed_hosts` 里配置，域名必须完全一致，且必须是 https。
  - 识别代码同时支持 schema.org Recipe 结构化数据和 SvelteKit `__data.json` 两种格式，以后放开别的网站时可以直接用。
  - 另外还会检查域名解析出的地址必须是公网地址，不能用来访问局域网或本机。
  - HTTPS 证书交给操作系统校验（依赖 `truststore`），结果和浏览器一致。电脑上装了 Norton 这类会扫描 HTTPS 的杀毒软件时，Python 默认的校验方式可能报"certificate has expired / verify failed"。遇到这种情况，先确认运行服务器的 Python 环境执行过 `pip install -e .`。
- `src/data/recipes.json` 里新增的食谱，下次启动时会自动导入已有数据库；在网页上删掉的内置食谱不会被重新加回来。

### 补货清单
- 标签上的红色数字是待买数量。
- 加入清单的方式：在本页直接添加；食材数量选"缺货"；食材点"吃完"；"今日一荤一素"里点"加入补货清单"；本页底部"快用完了"（数量为见底的食材）点"加入补货清单"。同名的不会重复添加。
- **买到了**：跳到食材页并预填好（预设食材会自动带上保质期），保存后自动从清单移除。
- **自动移除**：只要往冰箱里添加了**同名**食材（名字完全相同），补货清单里的这一项就会被自动删除，不管是不是从"买到了"进去的。
- 清单里的条目不算"冰箱里有"，推荐食谱时不会被当成已有食材。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/shopping` | 补货清单（数量为"缺货"的条目） |
| GET | `/api/foods` | 冰箱里的食材，不含缺货条目（带 `days_stored` 已存天数、`days_left`、`status`：expired / expiring / fresh / none；`expiry_date` 可为 null） |
| POST | `/api/foods` | 添加食材。`quantity: "缺货"` = 加入补货清单（同名已有则返回 `duplicate: true`）；其他数量会自动删掉补货清单里同名条目（返回 `restocked` 条数） |
| PUT | `/api/foods/{id}` | 修改食材 |
| DELETE | `/api/foods/{id}` | 删除食材 |
| GET | `/api/recipes` | 食谱列表 |
| POST | `/api/recipes` | 添加食谱 |
| POST | `/api/recipes/import` | 从链接识别食谱，body：`{"url": "..."}`，返回草稿（不保存），食材带 `role`：main / seasoning / skip |
| PUT | `/api/recipes/{id}` | 修改整道食谱（字段同添加；`type` 为 null 时按主料自动判断） |
| PATCH | `/api/recipes/{id}` | 修改荤/素，body：`{"type": "荤"}` |
| DELETE | `/api/recipes/{id}` | 删除食谱 |
| GET | `/api/recommend?max_missing=2&type=素` | 推荐食谱（`type` 可选；`max_missing=-1` 表示不限） |
| GET | `/api/daily?max_missing=2` | 今日一荤一素：`{"荤": [...], "素": [...]}`，各自按推荐顺序排列 |
| GET | `/api/presets` | 食材预设 |
| GET | `/api/version` | 当前版本：`{"name": "FridgeManager", "version": "1.26.11.0"}` |
