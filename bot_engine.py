import hashlib, base64, json, requests, random, math, socketio, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

GLOBAL_HISTORY = []
MAX_GLOBAL_HISTORY = 2000

GLOBAL_AI_WEIGHTS = {
    "trend": 1.0, "pattern": 1.0, "frequency": 1.0, "momentum": 1.0, "symmetry": 1.0,
    "alternating": 1.0, "fibonacci": 1.0, "chaos": 1.0, "shadow": 1.0,
    "markov1": 1.0, "markov2": 1.0, "markov3": 1.0,
    "rsi_indicator": 1.0, "macd_cross": 1.0, "pivot_reversal": 1.0, "cluster_3": 1.0,
    "parity": 1.0, "golden_ratio": 1.0, "quantum": 1.0,
    "anti_bait": 2.0, "smart_breaker": 2.0,
    "ngram_4": 1.5, "ngram_5": 1.5, "elliott_wave": 1.5, "contrarian": 2.0,
    "bollinger_bands": 1.5, "mean_reversion": 1.0, "mirror_reflection": 1.0,
    "martingale_trap": 1.5, "poisson_prob": 1.0, "harmonic_cycle": 1.0,
    "breakout_hunter": 1.5, "volume_fakeout": 1.5, "time_decay": 1.0,
    "neural_bias": 1.0, "twin_peaks": 1.0
}
GLOBAL_MODEL_STREAK = {k: 0 for k in GLOBAL_AI_WEIGHTS.keys()}

def md5_hash(t): return hashlib.md5(t.encode()).hexdigest()

def login_and_get_token(username, password):
    pw = md5_hash(password)
    url = f"https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw}&cp=R&cl=R&pf=web&at="
    try:
        r = requests.get(url, timeout=12); r.raise_for_status(); data = r.json()
        if not data.get("success"):
            return {"_error": f"Lỗi Game: {data.get('message','Sai thông tin')}"}
        sk = data["sessionKey"]; sk += "=" * ((4 - len(sk) % 4) % 4)
        sd = json.loads(base64.b64decode(sk).decode())
        nickname = sd.get("nickname") or sd.get("nickName")
        at = data["accessToken"]
        r2 = requests.post("https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at=",
            headers={"authority": "wlb.tele68.com", "content-type": "application/json"},
            json={"nickName": nickname, "accessToken": at}, timeout=12)
        lobby = r2.json(); token = lobby.get("token")
        if not token: return {"_error": "Lobby không trả JWT."}
        return {"token": token, "nickname": nickname,
                "money": lobby.get("remoteLoginResp", {}).get("money", 0)}
    except Exception as e:
        return {"_error": f"Lỗi kết nối: {e}"}

def make_prediction(history=None, last_preds_holder=None):
    history = history if history is not None else GLOBAL_HISTORY
    weights = GLOBAL_AI_WEIGHTS
    if len(history) < 10: return random.choice(["TAI", "XIU"])

    preds = {"TAI": 0.0, "XIU": 0.0}
    model_preds = {}
    last_item = history[-1]
    opp_item = "XIU" if last_item == "TAI" else "TAI"
    rs = "".join(["T" if x == "TAI" else "X" for x in history])
    streak = len(rs) - len(rs.rstrip(rs[-1]))

    model_preds["trend"] = last_item if history[-5:].count(last_item) >= 3 else opp_item
    model_preds["pattern"] = opp_item if rs.endswith(("TXTX","TTXX")) else last_item
    t1 = {"TAI":{"TAI":0,"XIU":0},"XIU":{"TAI":0,"XIU":0}}
    for i in range(len(history)-1): t1[history[i]][history[i+1]] += 1
    model_preds["markov1"] = "TAI" if t1[last_item]["TAI"] > t1[last_item]["XIU"] else "XIU"
    model_preds["markov2"] = "TAI" if history[-2:] == ["TAI","TAI"] else "XIU"
    model_preds["markov3"] = opp_item if history[-3:] == [last_item]*3 else model_preds["markov2"]
    model_preds["frequency"] = "XIU" if history[-20:].count("TAI") > 10 else "TAI"
    model_preds["momentum"] = "TAI" if sum([i+1 if r=="TAI" else -(i+1) for i,r in enumerate(history[-5:])]) > 0 else "XIU"
    model_preds["symmetry"] = opp_item if len(rs)>=6 and rs[-6:-3]==rs[-3:][::-1] else last_item
    model_preds["alternating"] = opp_item
    model_preds["fibonacci"] = opp_item if streak in [3,5,8,13] else last_item
    model_preds["chaos"] = opp_item if sum(1 for i in range(len(rs[-10:])-1) if rs[-10:][i]!=rs[-10:][i+1])>=7 else last_item
    model_preds["shadow"] = "TAI" if history[-50:].count("TAI")<25 else "XIU"
    rsi = rs[-10:].count("T")
    model_preds["rsi_indicator"] = "XIU" if rsi>=7 else ("TAI" if rsi<=3 else last_item)
    model_preds["macd_cross"] = "TAI" if rs[-3:].count("T")>(rs[-9:].count("T")/3) else "XIU"
    model_preds["pivot_reversal"] = history[-1] if history[-3]==history[-2] and history[-2]!=history[-1] else last_item
    model_preds["cluster_3"] = "TAI" if rs[-3:] in ["TTT","TXX","XTX","XXT"] else "XIU"
    model_preds["parity"] = opp_item if streak%2==0 else last_item
    model_preds["golden_ratio"] = "TAI" if (history[-30:].count("TAI")/30)<0.618 else "XIU"
    model_preds["quantum"] = random.choice(["TAI","XIU"])
    model_preds["anti_bait"] = opp_item if streak>=5 or rs.endswith("TXTXT") else last_item
    mx=1; cur=1
    for i in range(1,len(history)):
        if history[i]==history[i-1]: cur+=1
        else: mx=max(mx,cur); cur=1
    model_preds["smart_breaker"] = opp_item if streak>=mx-1 and streak>=3 else last_item
    l4=rs[-4:]; tc4=rs[:-1].count(l4+"T"); xc4=rs[:-1].count(l4+"X")
    model_preds["ngram_4"] = "TAI" if tc4>xc4 else ("XIU" if xc4>tc4 else opp_item)
    l5=rs[-5:]; tc5=rs[:-1].count(l5+"T"); xc5=rs[:-1].count(l5+"X")
    model_preds["ngram_5"] = "TAI" if tc5>xc5 else ("XIU" if xc5>tc5 else opp_item)
    model_preds["elliott_wave"] = last_item if rs.endswith("TXTXT") else ("XIU" if rs.endswith("TTXXTT") else opp_item)
    model_preds["contrarian"] = opp_item if streak in (4,6) else ("XIU" if rs[-6:]=="TXTXTX" else last_item)
    ma10 = rs[-10:].count("T")/10.0
    model_preds["bollinger_bands"] = "XIU" if ma10>=0.8 else ("TAI" if ma10<=0.2 else last_item)
    ttot = history[-100:].count("TAI") if len(history)>=100 else history.count("TAI")
    model_preds["mean_reversion"] = "TAI" if ttot < len(history[-100:])*0.45 else "XIU"
    model_preds["mirror_reflection"] = ("TAI" if rs[-8]=="T" else "XIU") if len(rs)>=8 else opp_item
    model_preds["martingale_trap"] = opp_item if streak in (3,7) else last_item
    model_preds["poisson_prob"] = "TAI" if history[-5:].count("TAI")%2==1 else "XIU"
    model_preds["harmonic_cycle"] = history[-4] if len(history)>=4 else opp_item
    model_preds["breakout_hunter"] = last_item if streak==1 and history[-2]==history[-3] else opp_item
    model_preds["volume_fakeout"] = last_item if len(rs)>=5 and rs[-5:] in ["TTTXT","XXXTX"] else opp_item
    model_preds["time_decay"] = opp_item
    model_preds["neural_bias"] = "TAI" if history[-7:].count("TAI")>3 else "XIU"
    model_preds["twin_peaks"] = opp_item if rs.endswith(("TTXTT","XXTXX")) else last_item

    if last_preds_holder is not None:
        last_preds_holder.clear(); last_preds_holder.update(model_preds)

    for m, p in model_preds.items():
        preds[p] += math.pow(weights.get(m, 1.0), 1.5)
    return "TAI" if preds["TAI"] > preds["XIU"] else "XIU"

def update_global_weights(actual_result, last_preds):
    global GLOBAL_AI_WEIGHTS, GLOBAL_MODEL_STREAK
    if not last_preds: return
    for m, p in last_preds.items():
        if p == actual_result:
            GLOBAL_MODEL_STREAK[m] += 1
            GLOBAL_AI_WEIGHTS[m] = min(20.0, GLOBAL_AI_WEIGHTS[m] + 0.5 + 0.2*GLOBAL_MODEL_STREAK[m])
        else:
            GLOBAL_MODEL_STREAK[m] = 0
            GLOBAL_AI_WEIGHTS[m] = max(0.1, GLOBAL_AI_WEIGHTS[m] - 2.5)
