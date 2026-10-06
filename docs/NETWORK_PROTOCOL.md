# 网络协议

浏览器只发送身份和动作。牌、底池和赢家由服务端决定。进行中的牌桌在内存里。已结束的手在 SQLite。

## HTTP

`GET /health` 返回 `{"status":"ok","service":"openpokerlab","database":"ok"}`。`database` 只表示 `SELECT 1` 成功。

房间：

- `POST /rooms` 建房，不自动入座。
- `POST /rooms/join` 用邀请码加入，得到 `guest_token`。
- `POST /rooms/{id}/sit` 入座。首次入座是 1000 娱乐筹码，买入限制打开时可以带 `amount`。
- `POST /rooms/{id}/stand`、`/leave`、`/chips`。
- `GET /rooms/{id}` 看房间。
- 房主：`POST /rooms/{id}/start`、`/pause`、`/settings`、`/bots`、`/bots/remove`。非房主是 HTTP 403。盲注和规则下一手生效。

历史和统计：`GET /hands`、`GET /hands/{id}`、`GET /hands/{id}/state?index=`、`GET /stats`。`/stats` 可带 `player`、`position`、`date_from`、`date_to`、`small_blind`、`big_blind`、`rules`、`street`。

求解：`GET /solver/health?adapter=`、`POST /solver/solve`。只有这次显式求解会写 `analysis_jobs` 和 `decision_analysis`。

分析：`GET /analyze/hands/{hand_id}`。训练：`GET /trainer/spots`、`GET /trainer/spots/{id}`、`POST /trainer/spots/{id}/answer`。

`GET /settings` 返回数据库路径、可选规则、机器人种类和变体，并带 `cash_settlement: false`。

错误体是 `{"type":"ERROR","payload":{"message":"..."}}`。

## WebSocket `/ws`

连接后服务端先发：

```json
{"type":"CONNECTED","payload":{"service":"openpokerlab"}}
```

这条连接没有牌，也没有房间状态。

## WebSocket `/ws/room`

第一条客户端消息：

```json
{"type":"JOIN","payload":{"guest_token":"..."}}
```

服务端消息：`ROOM_JOINED`、`PLAYER_JOINED`、`PLAYER_LEFT`、`PLAYER_RECONNECTED`、`HAND_STARTED`、`CARDS_DEALT`、`ACTION_REQUIRED`、`ACTION_RESULT`、`FLOP`、`TURN`、`RIVER`、`SHOWDOWN`、`HAND_COMPLETE`、`GAME_STATE`、`ERROR`。发两次打开时还有 `RIT_OFFER`、`RIT_VOTE`、`RIT_RESULT`。保险打开时有 `INSURANCE_OFFER`。

每个连接只收到自己的视角。对手底牌在摊牌前不下发，而且只公开走到摊牌的座位。旁观者遵守同样的隐藏规则，不能行动。

玩家动作：

```json
{"type":"PLAYER_ACTION","request_id":"...","payload":{"action":"raise","amount":120}}
```

`raise` 的 `amount` 是本街总额。`bet` 的 `amount` 是投入的筹码。发两次的投票是 `{"type":"RIT_VOTE","request_id":"...","payload":{"accept":true}}`。保险决定是 `{"type":"INSURANCE_DECISION","payload":{"accept":true}}`。时间银行打开时，`ACTION_REQUIRED` 带 `remaining_seconds` 和 `deadline`。

学习模式可以在 `GAME_STATE` 上附带单挑翻后的混合。竞技模式是默认，牌局中不附带。三人及以上进行中只给固定的不可用句子，不给混合。
