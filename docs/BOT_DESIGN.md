# 机器人

机器人在 `backend/app/bots/`。它们和人类走同一条 `act` 校验。它们不导入牌局对象、牌堆提供者或房间内部状态。

## 观察

`PokerBot.decide(observation)` 返回 `BotAction`。房间用 `player_view` 组装观察，内容和人类 WebSocket 能看到的一样：自己的底牌、公共牌、底池、筹码、合法动作、位置、街道、行动记录。没有对手底牌，没有牌堆，也没有 GTO 混合。

`BotAction.kind` 是 `fold`、`check`、`call`、`bet`、`raise` 或 `all_in`。`bet` 的数量是投入的筹码。`raise` 的数量是本街总额。轮到机器人时服务器立刻替它行动，所以时间银行不会把机器人超时弃牌。房主用 `POST /rooms/{id}/bots` 添加，用 `/bots/remove` 移除。座位有昵称。内部的 guest token 不返回给浏览器。

## RuleBot

`RuleBot` 用牌力、位置、底池赔率和门槛选动作，再混入一份带种子的随机合法动作。`mix` 默认 0.08。它只需要下出合法动作，不估计对手范围。

## EquityBot

`EquityBot` 用蒙特卡洛抽样估计自己的权益，再和底池赔率比较。参数是 `tightness`、`aggression`、`bluff_frequency`、`simulation_count` 和 `seed`。后位会略微降低所需权益。有效筹码、SPR 和位置影响下注还是跟注。抽样只用已知的公共牌和自己的底牌，不看别人的底牌。

## StrategyBot

`StrategyBot` 持有一个 `StrategyStore`。查找键是小盲、大盲、位置、以大盲计的筹码深度、公共牌和行动记录。命中就按那份混合抽样。没命中就交给 `EquityBot`。仓库里的样例是 `backend/app/bots/fixtures/btn_open.json`：按钮在空行动历史上开池到 6。
