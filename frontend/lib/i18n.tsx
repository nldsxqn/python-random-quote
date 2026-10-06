"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "zh" | "en";

const STORAGE_KEY = "openpokerlab.lang";

const zh: Record<string, string> = {
  Play: "打牌",
  Replay: "回放",
  Analyze: "分析",
  Trainer: "训练",
  Settings: "设置",
  Table: "牌桌",
  Home: "首页",
  Backend: "后端",
  WebSocket: "WebSocket",
  Checking: "检查中",
  Connected: "已连接",
  Disconnected: "未连接",
  "Connection status": "连接状态",
  Invite: "邀请码",
  host: "房主",
  spectator: "旁观",
  seat: "座位",
  Waiting: "等待",
  Pot: "底池",
  blinds: "盲注",
  Rake: "抽水",
  Bounty: "赏金",
  Run: "第",
  "Your cards": "你的底牌",
  hidden: "隐藏",
  Sit: "入座",
  Fold: "弃牌",
  Check: "过牌",
  Call: "跟注",
  Bet: "下注",
  Raise: "加注",
  "raise to": "加注到",
  amount: "数量",
  "Run it twice": "发两次",
  "Run once": "发一次",
  "Start hand": "开始一手",
  Resume: "继续",
  Pause: "暂停",
  "Small blind": "小盲",
  "Big blind": "大盲",
  "Update blinds": "更新盲注",
  Bot: "机器人",
  "Add bot": "添加机器人",
  Remove: "移除",
  "Rule changes apply on the next hand.": "规则修改从下一手开始生效。",
  Ante: "前注",
  "Ante mode": "前注方式",
  "Ante amount": "前注金额",
  normal: "每人",
  "bb ante": "大盲代下",
  "UTG straddle": "UTG straddle",
  "Straddle big blinds": "Straddle 大盲倍数",
  "Buy-in": "买入",
  "Minimum buy-in": "最低买入",
  "Maximum buy-in": "最高买入",
  "Buy-in unit": "买入单位",
  bb: "大盲",
  chips: "筹码",
  BB: "大盲",
  SB: "小盲",
  D: "庄",
  Hand: "手牌",
  "Current bet": "当前下注",
  "All-in": "全下",
  Chat: "聊天",
  "No messages": "没有消息",
  "Auto top-up": "自动补码",
  "Top-up threshold": "补码门槛",
  "Top-up target": "补码目标",
  "Time bank": "时间银行",
  "Time bank seconds": "时间银行秒数",
  "72o bounty": "72o 赏金",
  "Bounty big blinds": "赏金大盲倍数",
  "Rake percent": "抽水比例",
  "Rake cap": "抽水上限",
  "No flop no drop": "未翻牌不抽水",
  "no flop no drop": "未翻牌不抽水",
  "Bomb pot": "炸弹底池",
  "Bomb amount": "炸弹金额",
  "Save rules": "保存规则",
  Nickname: "昵称",
  "Create room": "创建房间",
  "Invite code": "邀请码",
  "Join room": "加入房间",
  Stack: "筹码",
  "Enter the raise-to total": "请填写加注到的总额",
  "Enter a bet amount": "请填写下注数量",
  "Not connected": "尚未连接",
  "Could not reach the server": "连不上服务器",
  "Something went wrong": "出了点问题",
  "Could not enter the room": "无法进入牌桌",
  "Could not load hands": "无法加载牌局",
  "Could not load that hand": "无法加载这手牌",
  "Could not load that action": "无法加载这个动作",
  "Request failed": "请求失败",
  "buy-in must be a positive integer": "买入必须是正整数",
  "Saved hands": "已保存的牌局",
  Hands: "牌局",
  "No saved hands yet.": "还没有保存的牌局。",
  "Hand replay": "牌局回放",
  Previous: "上一步",
  Next: "下一步",
  Stop: "停止",
  Autoplay: "自动播放",
  Flop: "翻牌",
  Turn: "转牌",
  River: "河牌",
  Showdown: "摊牌",
  "Hand id": "手牌编号",
  "Load hand": "加载牌局",
  Board: "公共牌",
  none: "无",
  "No strategy": "没有策略",
  Hero: "英雄",
  "No decisions to review.": "没有需要复盘的决策。",
  "That hand is not stored": "没有保存这手牌",
  street: "街道",
  position: "位置",
  severity: "严重程度",
  from: "从",
  to: "到",
  Street: "街道",
  Position: "位置",
  Severity: "严重程度",
  "From date": "开始日期",
  "To date": "结束日期",
  Filter: "筛选",
  "No saved spots yet.": "还没有保存的训练题。",
  "Your action": "你的动作",
  Original: "原来的动作",
  "EV loss": "EV 损失",
  "That action is not in this spot": "这个动作不在本题里",
  Database: "数据库",
  "Cash settlement": "现金结算",
  on: "开启",
  off: "关闭",
  "GTO mode": "GTO 模式",
  "Save GTO mode": "保存 GTO 模式",
  Variant: "变体",
  "Save variant": "保存变体",
  Straddle: "Straddle",
  "Save straddle": "保存 straddle",
  "Double-board bomb": "双面炸弹底池",
  "Simplified insurance": "简化保险",
  "Open a table from Play first": "请先在打牌页打开一桌",
  Saved: "已保存",
  "The table rejected that change": "牌桌拒绝了这次修改",
  competitive: "竞技",
  study: "学习",
  nlhe: "德州",
  short_deck: "短牌",
  utg: "UTG",
  mississippi: "Mississippi",
  custom: "自定义",
  rule: "规则机器人",
  equity: "权益机器人",
  strategy: "策略机器人",
  Language: "语言",
  "Buy-in amount": "买入筹码",
  "play-money chips": "娱乐筹码",
  "Limit": "限额",
  "nickname must be 1 to 24 characters": "昵称需要 1 到 24 个字符",
  "room not found": "找不到这间牌桌",
  "Field required": "还缺少必填项",
  "already seated": "已经入座",
  "already holding chips; add chips instead": "已经有筹码，请改为补码",
  "sit before adding chips": "请先入座再补码",
  "not seated": "还没有入座",
  "table is paused": "牌桌已暂停",
  "need at least 2 seated players with chips": "至少需要两名有筹码的入座玩家",
  "cannot pause during a hand": "手牌进行中不能暂停",
  "cannot sit during a hand": "手牌进行中不能入座",
  "cannot stand during a hand": "手牌进行中不能站起",
  "cannot leave during a hand": "手牌进行中不能离开",
  "cannot add chips during a hand": "手牌进行中不能补码",
  "cannot add a bot during a hand": "手牌进行中不能添加机器人",
  "only the host can add a bot": "只有房主可以添加机器人",
  "only the host can remove a bot": "只有房主可以移除机器人",
  "only the host can start a hand": "只有房主可以开始一手",
  "only the host can pause": "只有房主可以暂停",
  "only the host can change blinds": "只有房主可以改盲注",
  "that seat is not a bot": "这个座位不是机器人",
  "no open seat": "没有空位",
  "seat is taken": "座位已被占用",
  "seat is out of range": "座位超出范围",
  "unknown guest token": "找不到这个身份",
  "spectators cannot act": "旁观者不能行动",
  "no hand in progress": "当前没有进行中的手牌",
  "unknown bot": "未知的机器人",
  "unknown action": "未知动作",
  "added chips must be a positive integer": "补码必须是正整数",
  "Real-time multiway GTO analysis is not available. Post-hand analysis will be available after the hand.":
    "多人牌局暂不提供实时 GTO。本手结束后可以做赛后分析。",
  "Preflop is not solved as exact GTO.": "翻牌前不会被标成精确 GTO。",
  Good: "良好",
  Small: "小",
  Medium: "中",
  Large: "大",
  Critical: "严重",
  PREFLOP: "翻牌前",
  FLOP: "翻牌",
  TURN: "转牌",
  RIVER: "河牌",
  SHOWDOWN: "摊牌",
  HAND_COMPLETE: "本手结束",
  WAITING: "等待",
  SEATED: "已入座",
  ACTIVE: "在局",
  FOLDED: "已弃牌",
  ALL_IN: "全下",
  ELIMINATED: "已出局",
  fold: "弃牌",
  check: "过牌",
  call: "跟注",
  bet: "下注",
  raise: "加注",
  all_in: "全下",
  post: "下盲",
  deal: "发牌",
  complete: "结束",
};

const LanguageContext = createContext<{
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (text: string) => string;
} | null>(null);

export function localize(lang: Lang, text: string): string {
  if (!text || lang === "en") {
    return text;
  }
  const ranged = text.match(/^(buy-in|added chips) must be from (\d+) to (\d+)$/);
  if (ranged) {
    const label = ranged[1] === "buy-in" ? "买入" : "补码";
    return `${label}必须在 ${ranged[2]} 到 ${ranged[3]} 之间`;
  }
  const cap = text.match(/^stack cannot exceed (\d+)$/);
  if (cap) {
    return `筹码不能超过 ${cap[1]}`;
  }
  return zh[text] ?? text;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh") {
      setLang(saved);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) {
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang, ready]);

  const value = useMemo(
    () => ({
      lang,
      setLang,
      t: (text: string) => localize(lang, text),
    }),
    [lang],
  );

  return (
    <LanguageContext.Provider value={value}>
      <div className="lang-bar">
        <span className="note">{localize(lang, "Language")}</span>
        <button type="button" aria-pressed={lang === "zh"} onClick={() => setLang("zh")}>
          中文
        </button>
        <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
          English
        </button>
      </div>
      {children}
    </LanguageContext.Provider>
  );
}

export function useI18n(): { lang: Lang; setLang: (lang: Lang) => void; t: (text: string) => string } {
  const value = useContext(LanguageContext);
  if (!value) {
    throw new Error("useI18n must be used inside LanguageProvider");
  }
  return value;
}
