# OpenPokerLab

自托管的无限注德州扑克（NLHE）现金局实验平台。当前完成 **Phase 0** 到 **Phase 9**。牌局仍然是娱乐筹码：没有充值、提现或现金结算。Phase 6 到 Phase 8 是单决策 GTO、赛后分析和求解器边界。Phase 9 加上短牌、简化保险、双面炸弹底池、Mississippi 和自定义 straddle、单桌免费赛，以及 `/settings`。

## 用途声明

本项目仅供娱乐、研究与训练。不提供真实货币的充值、提现或现金结算，也不自动化对接第三方扑克室。牌局、买入、补码、赏金、保险和锦标赛赢家都是娱乐筹码。没有现金奖励。

## 页面

| 路径 | 作用 |
| --- | --- |
| `/` | 连接状态。 |
| `/play` | 建房、入座、行动。房主可以改规则、机器人、竞技或学习模式。 |
| `/replay` | 逐步回放已保存的手牌。 |
| `/analyze` | 查看一手的决策、策略、EV 和范围。 |
| `/trainer` | 练习已保存的失误。选出动作之后才显示频率和 EV。 |
| `/settings` | 数据库路径，以及当前牌桌的规则、机器人、GTO 模式和变体。 |

## 当前阶段

Phase 0 至 Phase 5 已完成。Phase 1 是 `backend/app/engine/` 里的标准 NLHE 现金局引擎：2–9 人、盲注、街道、摊牌、主池和边池。引擎不导入 FastAPI。牌力比较通过 PokerKit 的评估适配完成，牌局状态、下注和底池由本仓库自己实现。

Phase 2 在同一进程里组桌，不用 Redis。进行中的牌桌仍在内存里。身份是昵称、`guest_token` 和房间邀请码，没有密码。创建房间不会自动入座。入座后的起始筹码是 1000（娱乐筹码）。只有房主可以开始手牌、在两手之间暂停、以及修改盲注；盲注修改在下一手生效，不会改当前这一手。对局走 WebSocket `/ws/room`（不是 `/ws`）。服务端用引擎发牌并校验每一个动作。每个连接只收到自己的视角：对手底牌、牌堆和尚未发出的公共牌都不会下发；摊牌只公开走到摊牌的玩家。旁观者遵守同样的隐藏规则，并且不能行动。

浏览器打开 `http://localhost:3000/play` 即可建房或凭邀请码加入。首页 `http://localhost:3000` 仍只显示连接状态。

Phase 3 把可选规则做成插件。引擎仍不导入 FastAPI；具体规则在 `backend/app/rules/`。房间设置选择插件，房主在手牌进行中修改时，下一手才生效。全部默认关闭，关闭时牌局与 Phase 1 相同。

- **前注**：`normal` 是每位发到牌的玩家各下一份；`bb_ante` 是大盲替全桌下一份。前注在底牌发出前进入底池，不算这条街的下注。
- **Straddle**：UTG 是大盲左边的玩家下 `amount_bb` 倍大盲，翻前行动从他的左边开始。Mississippi 和自定义位置在 Phase 9 实现，见下文。
- **买入**：最小和最大，单位是 `bb` 或 `chips`。入座或补码时检查。没有真实货币钱包。
- **自动补码**：一手开始时，座位筹码低于门槛就补到目标，单位是大盲，并记下补了多少。这是娱乐筹码，不是现金。
- **时间银行**：截止时间由服务端持有。面对下注时超时弃牌，否则超时过牌。`ACTION_REQUIRED` 带剩余秒数。测试注入时钟，不会真的睡眠。
- **72o 赏金**：默认关闭。只有 72 不同花，而且必须在摊牌赢下。默认 `require_showdown` 为真，弃牌赢池不发赏金。本手发到牌的其他玩家各付 `payment_per_player_bb` 倍大盲。赏金在主池和边池之外，不改变那些底池的结果。筹码不够就付 `min(应付款, 剩余筹码)`，筹码不会变成负数，并标成部分支付。
- **发两次**：默认关闭。只有仍在争夺底池的玩家全部全下，并且已经过了翻牌或转牌，才发起。必须全体同意，否则只发一次。每个底池拆成两次，分别判胜负；除不尽时第一次多拿一枚。边池仍只属于原来有资格的玩家。消息是 `RIT_OFFER`、`RIT_VOTE`、`RIT_RESULT`。
- **抽水**：默认关闭。按百分比和上限，从派彩时的底池扣除并单独记录。`no_flop_no_drop` 表示翻牌前结束的一手不抽水。
- **炸弹底池**：默认关闭。每位发到牌的玩家下炸弹金额，这一手从翻牌开始。双面公共牌在 Phase 9 由 `boards: 2` 打开，见下文。

`/play` 上房主有一块紧凑的规则开关。被询问发两次的玩家可以选择是或否。赏金和抽水与底池分开显示。

Phase 4 让机器人坐进同一张桌子，并且只能走和人类一样的动作校验。机器人看不到服务端牌局对象、牌堆，也看不到别人的底牌。它拿到的观察和人类 WebSocket 视角相同：自己的底牌、公共牌、底池、筹码、合法动作、位置、街道和行动记录。房主可以添加或移除 RuleBot、EquityBot、StrategyBot。新座位有昵称，服务器内部使用一个 guest 身份。轮到机器人时，服务器立刻替它行动，所以时间银行不会把机器人超时弃牌。人类仍然用 `/play`。

- **RuleBot**：按牌力、位置、底池赔率和简单门槛行动，并混入一份带种子的随机选择。它只需要下出合法动作。
- **EquityBot**：用蒙特卡洛胜率对比底池赔率所要求的胜率，并参考有效筹码、SPR 和位置。参数是 tightness、aggression、bluff_frequency、simulation_count。
- **StrategyBot**：按局配置、位置、筹码深度、公共牌和行动记录查询 StrategyStore。命中就按那个混合抽样。没有命中就交给 EquityBot。仓库里有一份很小的按钮开池策略。

Phase 5 在一手结束时把整手写入 SQLite，机器人的手也写。回放不依赖还开着的房间。`/replay` 可以逐步查看，上一手动作、下一手动作、自动播放，以及跳到翻牌、转牌、河牌和摊牌。翻牌发出之前，回放里没有翻牌。对手的底牌只在摊牌那一步出现。请求者自己的底牌从一开始就能看到。`/play` 有指向回放的链接。

统计只从已保存的手计算，不写进预留的 `player_statistics` 表。可以按玩家、位置、日期、盲注和规则配置过滤。

- **手数**：发到牌的手数。
- **VPIP**：翻前主动投入筹码的手数除以手数。跟注、下注、加注、全下算。盲注、前注、straddle、炸弹、过牌和弃牌不算。
- **PFR**：翻前加注的手数除以手数。加注，以及把当前注额抬高的全下，算加注。只跟注的短码全下不算。
- **3Bet**：面对恰好一次翻前加注时再加注的次数，除以这样的机会。开池不算 3bet，4bet 也不算。没有机会时结果为空。
- **CBet**：翻前最后一位加注者在翻牌圈率先下注的次数，除以他还能率先下注的机会。没有机会时结果为空。
- **BB/100**：每手（结束筹码减开始筹码）除以大盲，再按 100 手平均。赏金和抽水已经反映在结束筹码里。
- **fold_to_3bet**：面对 3bet 时翻前弃牌的次数，除以面对 3bet 的机会。没有机会时为空。
- **wtsd**：走到摊牌的手数，除以看到翻牌的手数。没有看到翻牌时为空。
- **wssd**：摊牌时结束筹码大于开始筹码的次数，除以摊牌次数。没有摊牌时为空。
- **aggression_factor**：（下注次数 + 加注次数）/ 跟注次数。弃牌和过牌不算。没有跟注时为空。
- **fold_to_cbet**：面对翻牌持续下注时弃牌的次数，除以面对该下注的机会。没有机会时为空。
- **ev_bb**、**gto_ev_bb**、**ev_loss_bb**：该玩家已保存的 `decision_analysis` 行，按大盲求和。没有分析记录时为空，不会编造数字。
- **mistake_counts**：`good`、`small`、`medium`、`large`、`critical` 的次数。没有记录时五个都是 0。

可选的 `street` 只保留那条街有动作的手。攻击系数和分析合计也只算那条街。接口是 `GET /hands`、`GET /hands/{id}`、`GET /hands/{id}/state?index=`、`GET /stats`。表由 Alembic 迁移创建。`POST /solver/solve` 和赛后分析会写入 `analysis_jobs`、`decision_analysis`。失误写入 `trainer_spots`。`player_statistics` 不使用，统计在请求时计算。

Phase 6 增加 `backend/app/solver/`。`SolverAdapter.solve_spot` 接收一个决策点，返回动作、频率、EV、策略、可剥削度和 metadata。引擎不导入这个包，也不导入 FastAPI。

- **MockSolverAdapter**：固定的假混合，metadata 标明 `mock`。给测试和界面用，不是策略。
- **ReferenceSolverAdapter**：只解单挑、翻后、一个决策。河牌枚举给定范围，解过牌、下注尺度、以及面对下注时的弃牌和跟注，metadata.`exact` 为真，标签是 `heads-up one-decision`。翻牌和转牌在同一棵树里用蒙特卡洛胜率，`exact` 为假。多人或者翻前不会被标成精确 GTO。结果里不会出现 “Exact GTO”。
- **学习模式**可以在牌局里给英雄看混合。**竞技模式是默认**，牌局进行中不给混合。一手结束后可以分析。三人及以上进行中的牌局只显示这句话：`Real-time multiway GTO analysis is not available. Post-hand analysis will be available after the hand.`
- 机器人仍然只看玩家观察，看不到 GTO。显式的 `POST /solver/solve` 会把任务写进 `analysis_jobs` 和 `decision_analysis`。轮询牌桌不会写这些表。
- `/play` 上房主可以在竞技模式和学习模式之间切换。学习模式才出现 `gto-advice`。

`GET /solver/health` 和 `POST /solver/solve` 是求解接口。迁移 `analysis_002` 给分析表加了可空列。

Phase 7 增加 `/analyze` 和 `/trainer`。分析会重建已保存的一手，列出重要决策：大底池（至少 10 个大盲）、大下注、全下、3bet 底池、转牌和河牌。页面上有这条手牌的行动树、当时的桌子、策略、EV，以及 13×13 范围矩阵。EV 损失用大盲表示，等于最好动作的 EV 减去英雄所选动作的 EV。默认分档可以改：小于 0.1 是 Good，0.1 到 0.5 是 Small，0.5 到 2 是 Medium，2 到 5 是 Large，超过 5 是 Critical。0.1 算 Small，0.5 算 Medium，2 和 5 算 Large。三人及以上的结果标成 Approximate Analysis，不会写成 Exact GTO。

不是 Good 的决策会存成 TrainerSpot。训练页在你选出动作之前不显示频率、EV、原来的动作和 EV 损失。选出之后才显示你的动作、GTO 频率、EV、原来的动作和 EV 损失。可以按街道、位置、严重程度和日期过滤。迁移 `trainer_003` 给 `trainer_spots` 加了可空列。

Phase 8 的设计在 `docs/SOLVER_DESIGN.md`。`ZetaAdapter` 只返回不可用，仓库里没有 zeta 的代码。`MccfrSolverAdapter` 用外部抽样 MCCFR 重解同一棵单挑、翻后、一个决策的树。河牌可以 `exact`，标签仍是 `heads-up one-decision`。翻牌、转牌、多人、翻前都不是 Exact GTO。`GET /solver/health?adapter=zeta` 和 `adapter=mccfr` 可以选择适配器。

Phase 9 仍是娱乐筹码。

- **短牌**是单独的变体和评估器。牌从 6 到 A。A-6-7-8-9 是顺子。同花大于葫芦。标准德州的 `evaluate` 没有改，葫芦仍然大于同花。
- **保险**默认关闭。所有人在转牌全下之后、河牌发出之前，给出一份标成 simplified 的报价。保费来自权益。被报价的玩家可以接受或拒绝。接受只在已有底池里搬筹码，筹码不会变成负数。
- **双面炸弹底池**只有在 `boards` 为 2 时才发两套公共牌。每套牌单独分池。除不尽时第一套多拿一枚，和发两次的奇数筹码规则一样。
- **Straddle**：UTG 仍然有效。Mississippi 由按钮下 straddle，并且翻前最后行动。自定义 straddle 由选定的座位下，并且最后行动。
- **锦标赛**是一张娱乐筹码的冻结桌：盲注级别、筹码输光离场、最后一名持筹者获胜。没有现金奖励。
- **`/settings`** 可以看数据库路径，并在当前牌桌上改规则、机器人、GTO 模式和变体。

计划中的阶段到这里结束。Redis 仍然不是依赖。已实现的边界见 `docs/SOLVER_DESIGN.md`、`docs/ARCHITECTURE.md` 和 `AGENTS.md`。

## 在你自己的电脑上运行

需要 Python 3.12 或更新版本，以及 Node.js LTS（安装包里带 npm）。不需要 Visual Studio、Rust 或 Docker。

已经克隆过 `python-random-quote` 时，在仓库根目录执行：

```bat
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

还没有这份代码时：

```bat
git clone https://github.com/nldsxqn/python-random-quote.git
cd python-random-quote
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

脚本会创建 `backend\.venv`、安装依赖，并打开两个窗口：API 监听 `0.0.0.0:8000`，页面在 `http://localhost:3000`。本机打牌地址是 `http://localhost:3000/play`。同一局域网的另一台电脑打开 `http://<这台电脑的IP>:3000/play`。页面没有单独配置 API 地址时，会连当前网址的主机名、端口 8000。这两个窗口要保持开着。如果 Windows 防火墙询问，允许专用网络。数据库文件在 `data\openpokerlab.db`，第一次启动会自己建好。不要把 `.env.example` 里的地址抄进 `frontend\.env.local`，否则浏览器会一直请求 localhost。

## 在这台 Linux 上安装并运行

环境：Python 3.12（命令是 `python3`，没有 `python`）、pip、Node.js、npm。未安装 `uv`，也没有 `python3-venv`（`python3 -m venv` 会因缺少 `ensurepip` 失败）。不要为此安装系统包。下面用用户目录里的 `virtualenv` 创建项目虚拟环境。

```bash
cd /workspace

python3 -m pip install --user virtualenv
python3 -m virtualenv backend/.venv
backend/.venv/bin/pip install -e "./backend[dev]"

cd backend
.venv/bin/pytest
.venv/bin/ruff check .

# 另一个终端启动 API（默认 0.0.0.0:8000）
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd /workspace/frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:3000`。首页会请求 `http://localhost:8000/health`，并连接 `ws://localhost:8000/ws`。打牌页面是 `http://localhost:3000/play`，房间动作走 `ws://localhost:8000/ws/room`。

也可以把仓库根目录的 `.env.example` 复制为 `.env` 再改端口。不复制也可以：API 默认把 SQLite 放在 `data/openpokerlab.db`，前端默认使用上面的地址。Next.js 只会自动读取 `frontend/` 下的环境变量；若要改前端地址，把 `NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_WS_URL` 写进 `frontend/.env.local`。

## 在 Windows 10/11 上安装并运行

优先使用仓库根目录的 `scripts\dev.ps1`，见上面的「在你自己的电脑上运行」。下面是同一件事的手动步骤。

1. 安装 Python 3.12（安装时勾选 Add python.exe to PATH）和 Node.js LTS（自带 npm）。
2. 不需要 Visual Studio Build Tools、Rust、CMake 或 Docker。
3. 在仓库根目录：

```bat
py -3 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -e ".\backend[dev]"
cd backend
.venv\Scripts\pytest
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

另开一个终端：

```bat
cd frontend
npm install
npm run dev
```

SQLite 文件默认在仓库的 `data\openpokerlab.db`。若要改路径，在 `.env` 中设置，例如：

```bat
DATABASE_URL=sqlite:///C:/path/to/OpenPokerLab/data/openpokerlab.db
```

防火墙只需在局域网对局时放行私有网络。本机对局用 `localhost` 即可。打牌页面是 `http://localhost:3000/play`。

## 目录

| 路径 | 内容 |
| --- | --- |
| `backend/` | FastAPI 应用、NLHE 引擎与 pytest |
| `frontend/` | Next.js 首页、`/play` 牌桌与 `/replay` 回放 |
| `docs/` | 架构与进度 |
| `legacy/quote-bot/` | 原仓库里的 GitHub Learning Lab 引言机器人，与本项目无关，原样保留 |
| `data/` | 运行时 SQLite 文件（`*.db` 不入库） |

## 测试

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
cd /workspace/frontend
npm run lint
```

`pytest` 覆盖 Phase 0 的 `GET /health`、WebSocket `/ws`，Phase 1 的引擎，Phase 2 的房间，Phase 3 的规则插件，Phase 4 的机器人（含 RuleBot 一万手），以及 Phase 5 的手牌历史：指定牌局的结束筹码和公共牌能从库里读回，发两次的两副公共牌、赏金和抽水与底池分开存放，翻前回放不包含翻牌，统计夹具与手算结果一致，并且 Alembic 能在临时数据库上升级。

`GET /health` 应返回 `{"status":"ok","service":"openpokerlab","database":"ok"}`。WebSocket `/ws` 连接后第一条消息为 `{"type":"CONNECTED","payload":{"service":"openpokerlab"}}`。
