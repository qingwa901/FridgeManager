# 冰箱管家 FridgeManager

记录冰箱里的食材和保质期，并根据食谱库推荐现在能做的菜。

技术栈：Python + FastAPI + SQLite（标准库 `sqlite3`），前端是原生 HTML/CSS/JS，不需要构建。

## 目录结构

```
FridgeManager/
├─ config/
│  ├─ config.json        # 所有配置（端口、数据库路径、日志路径等）
│  └─ recipes.json       # 内置食谱（启动时导入数据库）
├─ docs/
│  ├─ README.md          # 本文档
│  └─ RELEASE_NOTES.md   # 更新日志（含版本号规则）
├─ VERSION               # 当前版本号，如 1.26.11.0
├─ src/
│  ├─ main.py            # 唯一的程序入口：python -m main。组装应用（FridgeManagerApp）、启动服务器（Server）
│  ├─ service.py         # Windows 服务包装：python -m service（子进程里运行 main.Server）
│  ├─ config.py          # Settings：读取 config/config.json
│  ├─ api/               # HTTP 接口，每个类一组路由
│  │  ├─ schemas.py               # 请求体（pydantic 模型）
│  │  ├─ food_api.py              # FoodApi：食材、补货清单
│  │  ├─ recipe_api.py            # RecipeApi：食谱库、从链接导入
│  │  ├─ group_api.py             # GroupApi：食材大类
│  │  ├─ recommend_api.py         # RecommendApi：推荐、今日一荤一素
│  │  ├─ system_api.py            # SystemApi：版本号、食材预设
│  │  └─ page_api.py              # PageApi：首页（JS/CSS 地址带内容指纹）
│  ├─ function/          # 业务功能
│  │  ├─ fridge_service.py        # FridgeService：食材、补货清单
│  │  ├─ recipe_service.py        # RecipeService：食谱库、内置食谱导入
│  │  ├─ group_service.py         # GroupService：食材大类
│  │  ├─ group_resolver.py        # GroupResolver：按大类匹配食材
│  │  ├─ recommender.py           # Recommender：推荐食谱
│  │  ├─ recipe_type_classifier.py # RecipeTypeClassifier：判断荤素
│  │  ├─ service_error.py         # ServiceError：业务错误（转成 HTTP 状态码）
│  │  └─ version_bumper.py        # VersionBumper：发布新版本
│  ├─ data/              # 数据读写，一张表一个类
│  │  ├─ database.py              # Database：连接、事务、建表
│  │  ├─ session.py               # Session：同一事务里的所有表
│  │  ├─ food_table.py            # FoodTable：foods
│  │  ├─ recipe_table.py          # RecipeTable：recipes
│  │  ├─ seed_imported_table.py   # SeedImportedTable：seed_imported
│  │  └─ ingredient_group_table.py # IngredientGroupTable：ingredient_groups
│  ├─ importer/          # 从网页链接识别食谱
│  │  ├─ recipe_importer.py       # RecipeImporter：抓取 → 识别 → 默认归类
│  │  ├─ safe_fetcher.py          # SafeFetcher：限制网站、公网地址、HTTPS 证书
│  │  ├─ json_ld_parser.py        # JsonLdParser：schema.org Recipe
│  │  ├─ sveltekit_parser.py      # SvelteKitParser：SvelteKit __data.json
│  │  ├─ text_parser.py           # TextParser：用时、"名称 用量"
│  │  ├─ import_diagnostics.py    # ImportDiagnostics：python -m importer <链接>
│  │  └─ recipe_import_error.py   # RecipeImportError
│  └─ static/            # 前端页面
├─ libs/
│  └─ CommonLib/         # 公共库 ZQCommonLib（git 子模块）：日志、FastAPI 应用的公共部分
├─ setup_venv.bat        # 新建 venv_{版本}_{时间} 并安装全部依赖
├─ venv_{版本}_{时间}/    # setup_venv.bat 生成的虚拟环境（不提交）
├─ logs/                 # 日志（自动创建）
└─ pyproject.toml        # 项目信息与依赖
```

数据库位置由 `config/config.json` 的 `database.path` 决定（可以放在项目外，例如 `D:\data\FridgeManager\fridge.db`）。

## 安装

需要 Python 3.13 及以上。

公共库 `libs/CommonLib` 是 git 子模块。第一次 clone 或拉取更新后，先把它下载 / 更新到项目记录的版本：

```powershell
cd D:\Code\FridgeManager
git submodule update --init
```

然后双击项目根目录的 `setup_venv.bat`，或在命令行运行：

```powershell
D:\Code\FridgeManager\setup_venv.bat
```

它会：
1. 用 `py -3`（没有就用 `python`）创建新的虚拟环境 `venv_{版本}_{日期时间}`，例如 `venv_1.26.11.0_20261121_180244`；
2. 升级 pip；
3. 以 `-e` 模式安装公共库：`pip install -e "libs\CommonLib[api]"`。公共库不在 PyPI 上，必须先装它，下一步 `pyproject.toml` 里的 `ZQCommonLib[api]` 才能满足。`[api]` 会一起装上 fastapi、uvicorn、pydantic 和 pywin32，版本由公共库统一锁定；
4. 按 `pyproject.toml` 安装其余依赖（`pip install -e .`）；
5. 检查依赖能否正常导入，最后打印运行命令。

因为是 `-e` 模式，公共库的代码改了（比如 `git submodule update` 之后）不需要重装；只有公共库的依赖变了才需要重新运行 `pip install -e "libs\CommonLib[api]"`，或者直接建一个新环境。

想用指定的 Python：`setup_venv.bat "C:\Path\to\python.exe"`。在脚本里调用、不想最后暂停：先 `set NO_PAUSE=1`。

每次升级都建一个新环境，旧环境留着。新版本有问题时，把服务指回旧环境即可回退。

## 运行

```powershell
cd src
..\venv_1.26.11.0_20261121_180244\Scripts\python.exe -m main
```

然后打开 `http://127.0.0.1:{端口}`（端口见 `config.json` 的 `server.port`），接口文档在 `/api/docs`。临时换端口：`-m main --port 8080`。

开发时在 PyCharm 里直接运行 `src/main.py` 也可以，效果相同。

## 部署为 Windows 服务

`src/service.py` 用 pywin32（已包含在依赖里）把服务器包装成 Windows 服务。它只负责服务的启动和停止，**不负责注册**，服务由你手动注册。监听地址、端口等照常在 `config/config.json` 里配置。

```powershell
cd D:\Code\FridgeManager\src
..\venv_1.26.11.0_20261121_180244\Scripts\python.exe -m service debug   # 在控制台按服务方式运行，Ctrl+C 停止
```

`python -m service` 不带参数时，由 Windows 服务管理器启动。

### 工作方式

- **父进程**（`service.py`）只做服务控制，导入的东西很少，能尽快连上服务管理器。
- **子进程**里运行 `main.Server`（uvicorn + FastAPI）。
- **停止**（服务停止，或系统关机时的 PRESHUTDOWN）：先通知子进程**优雅关闭**，日志里会记录"服务停止"和"服务器已退出"。10 秒内没退出，再用 `taskkill /T` 结束整个进程树。服务管理器会一直收到"正在停止"的进度，不会误判为卡死。重复收到停止请求只处理一次。
- **服务器自己退出**（比如端口被占用、配置写错）：服务会报告失败，不会空转着一直显示"正在运行"。可以在服务属性的"恢复"页里设置失败后自动重启。
- **日志**：服务器运行日志写入 `logs/fridgemanager_{启动时间}.log`；服务的启动、停止和失败会写入事件查看器（Windows 日志 → 应用程序）。

### 手动注册（管理员 PowerShell）

示例（把环境目录换成实际的）：

```powershell
New-Service -Name FridgeManager -DisplayName "冰箱管家 FridgeManager" -StartupType Automatic `
  -BinaryPathName '"D:\Code\FridgeManager\venv_1.26.11.0_20261121_180244\Scripts\python.exe" "D:\Code\FridgeManager\src\service.py"'
```

注意：
- **服务的工作目录是 `C:\Windows\System32`**，不是 `src`。所以服务程序里要写 `service.py` 的**完整路径**（如上）。如果坚持用 `python.exe -m service`，需要给服务加环境变量 `PYTHONPATH`，否则会找不到模块：
  ```powershell
  Set-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Services\FridgeManager -Name Environment -Type MultiString -Value 'PYTHONPATH=D:\Code\FridgeManager\src'
  ```
- 服务名请用 `FridgeManager`，和 `service.py` 里的 `_svc_name_` 保持一致。
- **运行账户**：默认是 LocalSystem，要能访问数据库所在目录（如 `D:\data\FridgeManager`）和 Python 安装目录。LocalSystem 默认都能访问。
- **防火墙**：`server.host` 为 `0.0.0.0` 时，要让局域网访问，需要放行端口（改成你的实际端口）：
  ```powershell
  New-NetFirewallRule -DisplayName "FridgeManager" -Direction Inbound -Protocol TCP -LocalPort 7922 -Action Allow
  ```

### 升级 / 回退

1. 运行 `setup_venv.bat`，建一个新环境。
2. 停止服务。
3. 在服务的注册表项 `HKLM:\SYSTEM\CurrentControlSet\Services\FridgeManager` 里，把 `ImagePath` 改成新环境的 `python.exe`；也可以用 `sc.exe config FridgeManager binPath= ...`。
4. 启动服务。

回退时，把 `ImagePath` 改回旧环境即可。

## 版本

版本号规则为 `1.{年份后两位}.{月份}.{当月序号}`，当月第一个版本序号为 0，例如 `1.26.11.0`、`1.26.11.1`。版本号保存在根目录 `VERSION` 文件，网页底部会显示当前版本，更新内容见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

发布新版本：

```powershell
cd src
..\.venv\Scripts\python.exe -m function.version_bumper --dry-run   # 先看看下一个版本号
..\.venv\Scripts\python.exe -m function.version_bumper             # 写入 VERSION，并在更新日志顶部插入新版本标题
```

## 配置 `config/config.json`

| 键 | 说明 | 默认 |
|---|---|---|
| `server.host` / `server.port` | 监听地址 / 端口 | `127.0.0.1` / `8000` |
| `database.path` | SQLite 文件路径 | `data/fridge.db` |
| `log.dir` | 日志目录（旧配置的 `log.path` 也能用，取它所在的目录） | `logs` |
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

日志由公共库（`common_lib.api.setup_api_logging`）配置：

- 同时输出到控制台和 `log.dir` 目录下的 `fridgemanager_{启动时间}.log`（如 `fridgemanager_261122_010608.log`），每天午夜轮转。
- 每行的格式：`时间 - 级别 - 线程 - 类名 - [请求 ID] - 内容`。类名就是写日志的类（如 `FridgeService`、`RecipeTable`）。请求 ID 取自请求头 `ID-Request`，网页不带这个头，所以显示为 `[]`。
- 内容包括：启动/停止、每个请求的路径和耗时（`MiddleWare`）、出错的请求（方法、路径、状态码、原因）、食材和食谱的增删改、推荐结果数量、未捕获的异常堆栈。
- 超过 `retention_days`（默认 14 天）的旧日志会自动删除：启动时和每次轮转时都会清理。升级前留下的 `fridgemanager.log.*` 也会按同样的规则清理掉。

## 出错时的返回格式

接口出错时返回公共库的错误格式，HTTP 状态码为 404（不存在）、409（重名）或 422（参数不对）：

```json
{"Error": {"Title": "Not Found", "Method": "/api/foods/99", "ErrorMsg": "食材不存在"}}
```

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
- 匹配规则：名字**完全相同**才算匹配。不按字面包含匹配，所以"葱"不会匹配"洋葱"，"鸡"不会匹配"鸡蛋"。想让几种食材互相通用，用下面的"食材大类"。
- **食材大类**：食谱主料写大类名（如"菌菇"），冰箱里有大类里的任何一样（如"干香菇""羊角菇"）就算有，推荐卡片上显示成"菌菇（干香菇）"。食谱写具体食材（如"香菇"）时不会用同类的其他食材代替。见下方"食材大类"。
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
  - **导入时报"HTTPS 证书校验失败"怎么查**：在出问题的那台机器上，用服务器所用的同一个环境运行：
    ```powershell
    cd <项目>\src
    <环境>\Scripts\python.exe -m importer "https://pullit.up.railway.app/recipes/<某个菜谱>"
    ```
    它会打印 Python 环境、本机时间、两种证书校验方式的结果、网站实际返回的证书（签发者、有效期），最后做一次导入测试。常见原因：
    - 环境里没装 `truststore`；
    - 本机时间不对；
    - 杀毒软件（如 Norton）替换了证书，而程序作为 Windows 服务运行时，用的是系统账户，看不到只装在个人账户下的根证书。
  - HTTPS 证书交给操作系统校验（依赖 `truststore`），结果和浏览器一致。电脑上装了 Norton 这类会扫描 HTTPS 的杀毒软件时，Python 默认的校验方式可能报"certificate has expired / verify failed"。遇到这种情况，先确认运行服务器的 Python 环境执行过 `pip install -e .`。
- `config/recipes.json` 里新增的食谱，下次启动时会自动导入已有数据库；在网页上删掉的内置食谱不会被重新加回来。

### 食材大类（右上角齿轮 ⚙）
- 一个大类包含多种具体食材，比如"菌菇"包含香菇、羊角菇、平菇、金针菇……第一次启动时会预置"菌菇"作为示例，之后可以在网页上随意增删改，改完立即生效，不用重启。
- 大类里的食材也要名字完全相同才算："干香菇"和"香菇"是两样，冰箱里会出现的叫法都要列上。
- 大类里可以写另一个大类名（比如"干货"包含"菌菇""腐竹"），会层层展开；不允许互相包含。
- 大类改名时，其他大类里引用它的地方会一起改；**食谱里写的旧名字不会自动改**，需要自己编辑食谱。
- 编辑食谱时，食材名输入框会提示大类名；推荐和食谱卡片上，大类名带虚线框，鼠标悬停可以看到包含哪些食材。
- 冰箱页的名称下拉也会列出大类里的食材（"大类里的食材"分组），输入"菇"就能选到"羊角菇"。
- 补货清单里写大类名（如"菌菇"）时，往冰箱里添加其中任何一样（如"羊角菇"），这一项也会被自动删除。

### 外观
- 深色模式：跟随手机 / 电脑系统的夜间模式自动切换，切换时页面会实时变化，不需要刷新。日期选择器、下拉框等原生控件和手机浏览器地址栏也会一起变色。
- 页头右上角的主题按钮可以在 **自动 → 浅色 → 深色** 之间切换，选择保存在当前浏览器里。按钮上的"自动（浅色/深色）"显示的是浏览器报告的系统模式。
  - 如果手机开了夜间模式，按钮却显示"自动（浅色）"，说明这个浏览器没有把系统夜间模式告诉网页。这时可以手动选"深色"，或者在浏览器设置里把主题改成"跟随系统"。比如安卓 Chrome：设置 → 主题 → 系统默认。
- 颜色都定义在 `src/static/style.css` 开头的变量里（浅色一套、深色一套），要调色只改那里即可。
- 网页引用 `style.css` / `app.js` 时会自动带上内容指纹（如 `app.js?v=8325b5ca55`），文件一改地址就变。所以更新网页后不需要清手机缓存，刷新即可拿到新版本（只要服务器是新代码）。

### 补货清单
- 标签上的红色数字是待买数量。
- 加入清单的方式：在本页直接添加；食材数量选"缺货"；食材点"吃完"；"今日一荤一素"里点"加入补货清单"；本页底部"快用完了"（数量为见底的食材）点"加入补货清单"。同名的不会重复添加。
- **买到了**：跳到食材页并预填好（预设食材会自动带上保质期），保存后自动从清单移除。
- **自动移除**：只要往冰箱里添加了**同名**食材（名字完全相同），补货清单里的这一项就会被自动删除，不管是不是从"买到了"进去的。清单里是大类名（如"菌菇"）时，添加其中任何一样（如"羊角菇"）也会删除。
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
| GET | `/api/recommend?max_missing=2&type=素` | 推荐食谱（`type` 可选；`max_missing=-1` 表示不限）。`used`：`{食谱食材: 实际用到的冰箱食材}`，只列名字不同的，如 `{"菌菇": "干香菇"}` |
| GET | `/api/groups` | 食材大类：`[{id, name, members, expanded}]`，`expanded` 为展开嵌套大类后的全部名字 |
| POST | `/api/groups` | 添加大类，body：`{"name": "菌菇", "members": ["香菇", "羊角菇"]}`；重名 409，互相包含 422 |
| PUT | `/api/groups/{id}` | 修改大类（改名时同步其他大类里的引用） |
| DELETE | `/api/groups/{id}` | 删除大类 |
| GET | `/api/daily?max_missing=2` | 今日一荤一素：`{"荤": [...], "素": [...]}`，各自按推荐顺序排列 |
| GET | `/api/presets` | 食材预设 |
| GET | `/api/version` | 当前版本：`{"name": "FridgeManager", "version": "1.26.11.0"}` |
