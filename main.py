# -*- coding: utf-8 -*-
"""
Bot d'ACCES - entonnoir 2 canaux Telegram (affiliation Zoomex).

Role : onboarder les prospects et gerer le gating SEQUENTIEL des 2 canaux prives.
  TG #1 "Le Tableau de Chasse" : 1re porte. Reserve aux UID inscrits sous le lien
                                 Zoomex d'Alan (verifie a la main par Alan).
  TG #2 "Le Desk"              : 2e porte. Reserve aux membres du Tableau qui ont
                                 atteint le volume mini (verifie a la main par Alan).

Flux (MVP, Alan dans la boucle) :
  ETAPE 1 - entree dans Le Tableau de Chasse
    1. Le prospect ouvre le bot -> /start -> accueil + lien d'affiliation.
    2. Il s'inscrit sur Zoomex via le lien, puis envoie son UID au bot.
    3. Le bot envoie a Alan (DM) une carte : [Valider (Tableau)] [Refuser].
    4. Sur "Valider", le bot cree un lien d'invitation usage unique (24h) vers
       Le Tableau de Chasse et l'envoie au prospect.
  ETAPE 2 - montee vers Le Desk
    5. Depuis Le Tableau de Chasse, le membre clique un lien deep-link
       (t.me/AlanTradingAccessBot?start=desk) -> le bot recoit "/start desk".
    6. Le bot envoie a Alan une carte : [Debloquer Le Desk] [Pas encore].
    7. Sur "Debloquer", le bot cree un lien usage unique (24h) vers Le Desk.

Conception : tout est pilote par variables d'environnement (aucun secret en dur).
Stack : requests seul. Etat persistant en JSON sur le volume Railway /data.

Brique d'extension (Phase 4) : la fonction verify_uid() est le SEUL point a changer
quand l'Excel Zoomex live sera dispo (de "demander a Alan" a "lire l'Excel").
"""
import json
import os
import time
import datetime as dt

import requests

# ----------------------------------------------------------------------
# Configuration (variables d'environnement, jamais en clair)
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("ACCESS_BOT_TOKEN", "")            # token BotFather du bot d'acces
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "1544682648")  # DM d'Alan (recoit les cartes)
TG1_CHAT_ID = os.environ.get("TG1_CHAT_ID", "")              # Le Tableau de Chasse (-100...)
TG2_CHAT_ID = os.environ.get("TG2_CHAT_ID", "")              # Le Desk (-100...)
AFFILIATE_LINK = os.environ.get("ZOOMEX_AFFILIATE_LINK", "https://www.zoomex.com/")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
if not os.path.isdir(DATA_DIR):
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))   # fallback local (tests PC)
STATE_PATH = os.path.join(DATA_DIR, "access_members.json")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_TIMEOUT = 50          # long-polling getUpdates (secondes)
UID_MIN_DIGITS = 6         # un UID Zoomex plausible = au moins 6 chiffres
INVITE_TTL_SECONDS = 24 * 3600   # les liens d'invitation expirent apres 24h


# ----------------------------------------------------------------------
# Journalisation simple (stdout = Deploy Logs Railway)
# ----------------------------------------------------------------------
def _log(msg):
    ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} UTC+7] {msg}", flush=True)


# ----------------------------------------------------------------------
# Etat persistant (JSON sur /data)
#   members : { "<tg_user_id>": {uid, username, tier, status, requested_at, decided_at} }
#             status : pending -> approved (Tableau) -> desk_pending -> desk_approved
#                      (ou refused)
#   pending : { "<req_id>": {tg_user_id, username, uid, kind} }  kind = tableau | desk
#   offset  : dernier update_id traite (reprise propre apres redemarrage)
#   seq     : compteur d'id de requete
# ----------------------------------------------------------------------
def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            st = json.load(f)
    except (FileNotFoundError, ValueError):
        st = {}
    st.setdefault("members", {})
    st.setdefault("pending", {})
    st.setdefault("offset", 0)
    st.setdefault("seq", 0)
    return st


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)   # ecriture atomique


# ----------------------------------------------------------------------
# Appels Telegram
# ----------------------------------------------------------------------
def tg(method, **params):
    try:
        r = requests.post(f"{API}/{method}", data=params, timeout=POLL_TIMEOUT + 10)
        return r.json()
    except Exception as e:
        _log(f"  Telegram {method} echec: {e}")
        return {"ok": False, "error": str(e)}


def send(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True}
    if reply_markup is not None:
        params["reply_markup"] = json.dumps(reply_markup)
    return tg("sendMessage", **params)


def create_single_use_invite(chat_id, label):
    """Lien d'invitation a usage unique (member_limit=1) + expiration 24h."""
    res = tg("createChatInviteLink", chat_id=chat_id, member_limit=1,
             expire_date=int(time.time()) + INVITE_TTL_SECONDS, name=label[:32])
    if res.get("ok"):
        return res["result"]["invite_link"]
    _log(f"  createChatInviteLink KO pour {chat_id}: {res}")
    return None


# ----------------------------------------------------------------------
# Verification de l'UID (POINT D'EXTENSION Phase 4)
#   MVP : on ne tranche pas ici, c'est Alan qui valide via les boutons.
#   Plus tard : lire l'Excel Zoomex -> renvoyer la decision automatiquement.
# ----------------------------------------------------------------------
def verify_uid(uid):
    """Renvoie la decision accordable sans intervention humaine.
    MVP : None = on defere a la validation manuelle d'Alan.
    Phase 4 (Excel) : renverra "okt" (Tableau) ou "no" (refus)."""
    return None


# ----------------------------------------------------------------------
# Messages (vocabulaire public : "Le Tableau de Chasse", "Le Desk",
#           "mon detecteur de squeeze" ; JAMAIS "H22")
# ----------------------------------------------------------------------
WELCOME = (
    "👋 Bienvenue ! Tu es à l'entrée de mon univers de trading.\n\n"
    "Ici je partage mes RÉSULTATS en toute transparence, trade après "
    "trade : mes gains ET mes pertes, rien de caché. Ça s'appelle "
    "<b>Le Tableau de Chasse</b>, et c'est ta première porte.\n\n"
    "(Pour les plus sérieux, il y aura ensuite <b>Le Desk</b> : mes "
    "signaux premium en direct. Mais une chose à la fois 😉)\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Pour entrer dans Le Tableau de Chasse, 2 étapes simples :\n\n"
    "1️⃣ Inscris-toi sur Zoomex via mon lien :\n{link}\n\n"
    "2️⃣ Reviens ici et envoie-moi ton <b>UID Zoomex</b> "
    "(le numéro de ton compte).\n\n"
    "Je vérifie et je t'ouvre la porte. 🚀"
)

ASK_UID = (
    "Pour te donner accès, j'ai besoin de ton <b>UID Zoomex</b> "
    "(uniquement le numéro).\n\n"
    "📍 Où le trouver : dans ton compte Zoomex, en haut de ton profil. "
    "Copie-le et colle-le ici."
)

UID_RECEIVED = (
    "✅ Bien reçu, merci !\n"
    "Je vérifie ton inscription sous mon lien. Je reviens vers toi "
    "très vite avec ton accès. 🔥"
)

REFUSED = (
    "Hmm, je n'ai pas retrouvé ton inscription sous mon lien Zoomex.\n\n"
    "Vérifie que tu t'es bien inscrit via MON lien :\n{link}\n\n"
    "Puis renvoie-moi ton UID. Si ça coince, écris-moi."
)

TABLEAU_GRANTED = (
    "🎉 C'est bon, bienvenue dans Le Tableau de Chasse !\n\n"
    "Ton lien d'entrée (usage unique, valable 24h, ne le partage pas) :\n"
    "🎯 {link}\n\n"
    "Installe-toi, regarde mes résultats, et lis le message épinglé : "
    "il t'explique comment débloquer Le Desk (mes signaux premium en "
    "direct), l'étape d'après. 🔥"
)

DESK_REQUEST_ACK = (
    "🔓 Tu veux débloquer Le Desk ? Bien joué d'être arrivé jusqu'ici.\n\n"
    "Je transmets ta demande à Alan, qui vérifie ton volume "
    "(10 000 $ minimum sous mon lien). Si c'est bon, je t'envoie ton "
    "accès au Desk juste après.\n\n"
    "✅ Demande envoyée, je reviens vers toi très vite. 🔥"
)

DESK_GRANTED = (
    "🎉 Bienvenue dans Le Desk !\n\n"
    "Ton lien d'entrée (usage unique, valable 24h, ne le partage pas) :\n"
    "💰 {link}\n\n"
    "Tu reçois maintenant mes signaux premium en direct. Lis bien le "
    "message épinglé du Desk avant de trader. 🚀"
)

DESK_NOT_YET = (
    "Tu n'as pas encore atteint les 10 000 $ de volume sous mon lien.\n"
    "Continue, et reviens cliquer sur le bouton quand c'est bon. "
    "Chaque trade te rapproche du Desk. 💪"
)

ALREADY_TABLEAU = (
    "Tu as déjà accès au Tableau de Chasse ✅.\n\n"
    "Pour débloquer Le Desk (mes signaux premium en direct), atteins "
    "10 000 $ de volume sous mon lien, puis clique sur le lien "
    "« débloquer Le Desk » dans le canal. Un souci ? Écris-moi."
)

ALREADY_DESK = (
    "Tu as déjà accès au Desk ✅. Un souci avec ton lien ? Écris-moi."
)

DESK_BEFORE_TABLEAU = (
    "Avant Le Desk, il faut d'abord entrer dans Le Tableau de Chasse 🙂\n\n"
    "Inscris-toi sur Zoomex via mon lien, envoie-moi ton UID, et je "
    "t'ouvre la première porte :\n{link}"
)


def admin_card(req_id, username, uid, tg_user_id):
    """Carte de validation d'entree au Tableau de Chasse (etape 1)."""
    txt = (
        "🆕 <b>Demande d'accès : Le Tableau de Chasse</b>\n"
        f"UID Zoomex : <code>{uid}</code>\n"
        f"Telegram : {username} (id <code>{tg_user_id}</code>)\n\n"
        "Vérifie : UID bien inscrit sous ton lien Zoomex ?"
    )
    kb = {"inline_keyboard": [[
        {"text": "✅ Valider (Tableau)", "callback_data": f"okt:{req_id}"},
        {"text": "❌ Refuser", "callback_data": f"no:{req_id}"},
    ]]}
    return txt, kb


def admin_desk_card(req_id, username, uid, tg_user_id):
    """Carte de deblocage du Desk (etape 2)."""
    txt = (
        "🔓 <b>Demande : LE DESK</b>\n"
        f"UID Zoomex : <code>{uid}</code>\n"
        f"Telegram : {username} (id <code>{tg_user_id}</code>)\n\n"
        "Vérifie : volume ≥ 10 000 $ sous ton lien ?"
    )
    kb = {"inline_keyboard": [[
        {"text": "✅ Débloquer Le Desk", "callback_data": f"okd:{req_id}"},
        {"text": "❌ Pas encore", "callback_data": f"nod:{req_id}"},
    ]]}
    return txt, kb


# ----------------------------------------------------------------------
# Traitement des updates
# ----------------------------------------------------------------------
def _username_of(from_user):
    if from_user.get("username"):
        return "@" + from_user["username"]
    return from_user.get("first_name", "membre")


def handle_message(st, msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    from_user = msg.get("from", {})
    user_id = str(from_user.get("id"))
    username = _username_of(from_user)
    text = (msg.get("text") or "").strip()

    # Commandes admin (depuis le DM d'Alan)
    if str(chat_id) == str(ADMIN_CHAT_ID) and text.startswith("/"):
        if text.startswith("/members"):
            members = st["members"]
            if not members:
                send(chat_id, "Aucun membre enregistre pour l'instant.")
            else:
                lines = ["<b>Membres</b> :"]
                for uid_rec in members.values():
                    lines.append(f"- UID <code>{uid_rec.get('uid')}</code> · "
                                 f"{uid_rec.get('username')} · {uid_rec.get('tier')} · "
                                 f"{uid_rec.get('status')}")
                send(chat_id, "\n".join(lines[:60]))
        return

    # /start cote prospect (avec payload eventuel : "/start desk")
    if text.startswith("/start"):
        payload = text[len("/start"):].strip().lower()
        if payload == "desk":
            handle_desk_request(st, chat_id, user_id, username)
        else:
            send(chat_id, WELCOME.format(link=AFFILIATE_LINK))
        return

    rec = st["members"].get(user_id)

    # Membre deja approuve (Tableau ou Desk) qui ecrit librement
    if rec and rec.get("status") in ("approved", "desk_pending"):
        send(chat_id, ALREADY_TABLEAU)
        return
    if rec and rec.get("status") == "desk_approved":
        send(chat_id, ALREADY_DESK)
        return

    # On attend un UID : un message majoritairement numerique
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) >= UID_MIN_DIGITS and len(digits) >= len(text) - 2:
        uid = digits
        st["seq"] += 1
        req_id = str(st["seq"])
        st["pending"][req_id] = {"tg_user_id": user_id, "username": username,
                                 "uid": uid, "kind": "tableau"}
        st["members"][user_id] = {
            "uid": uid, "username": username, "tier": "-", "status": "pending",
            "requested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        save_state(st)

        # Tentative d'auto-verification (Phase 4) ; sinon on defere a Alan.
        auto = verify_uid(uid)
        if auto is None:
            txt, kb = admin_card(req_id, username, uid, user_id)
            send(ADMIN_CHAT_ID, txt, reply_markup=kb)
            send(chat_id, UID_RECEIVED)
        else:
            apply_decision(st, req_id, auto)
        return

    # Sinon : on reexplique
    send(chat_id, ASK_UID)


def handle_desk_request(st, chat_id, user_id, username):
    """Le membre (deja dans le Tableau) demande l'acces au Desk via /start desk."""
    rec = st["members"].get(user_id)
    if not (rec and rec.get("status") in ("approved", "desk_pending", "desk_approved")):
        send(chat_id, DESK_BEFORE_TABLEAU.format(link=AFFILIATE_LINK))
        return
    if rec.get("status") == "desk_approved" or rec.get("tier") == "tg1_tg2":
        send(chat_id, ALREADY_DESK)
        return

    uid = rec.get("uid", "?")
    st["seq"] += 1
    req_id = str(st["seq"])
    st["pending"][req_id] = {"tg_user_id": user_id, "username": username,
                             "uid": uid, "kind": "desk"}
    rec["status"] = "desk_pending"
    save_state(st)

    txt, kb = admin_desk_card(req_id, username, uid, user_id)
    send(ADMIN_CHAT_ID, txt, reply_markup=kb)
    send(chat_id, DESK_REQUEST_ACK)


def apply_decision(st, req_id, decision):
    """decision : 'okt' (valide Tableau) | 'no' (refus Tableau) |
                  'okd' (debloque Desk)  | 'nod' (Desk pas encore)."""
    pend = st["pending"].get(req_id)
    if not pend:
        return "Demande introuvable (deja traitee ?)."
    user_id = pend["tg_user_id"]
    uid = pend["uid"]
    rec = st["members"].setdefault(user_id, {"uid": uid, "username": pend["username"]})
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    if decision == "no":
        rec.update(status="refused", tier="-", decided_at=now)
        send(user_id, REFUSED.format(link=AFFILIATE_LINK))
        st["pending"].pop(req_id, None)
        save_state(st)
        return "Refuse (Tableau), prospect notifie."

    if decision == "nod":
        rec.update(status="approved", decided_at=now)   # reste membre Tableau
        send(user_id, DESK_NOT_YET)
        st["pending"].pop(req_id, None)
        save_state(st)
        return "Desk refuse (pas encore), membre notifie."

    if decision == "okt":
        if not TG1_CHAT_ID:
            return "TG1 (Tableau) non configure."
        link = create_single_use_invite(TG1_CHAT_ID, f"uid {uid}")
        if not link:
            return "Lien Tableau non cree (bot admin du canal ?)."
        rec.update(status="approved", tier="tg1", decided_at=now)
        st["pending"].pop(req_id, None)
        save_state(st)
        send(user_id, TABLEAU_GRANTED.format(link=link))
        return "Approuve (Tableau), lien envoye."

    if decision == "okd":
        if not TG2_CHAT_ID:
            return "TG2 (Desk) non configure."
        link = create_single_use_invite(TG2_CHAT_ID, f"uid {uid} desk")
        if not link:
            return "Lien Desk non cree (bot admin du canal ?)."
        rec.update(status="desk_approved", tier="tg1_tg2", decided_at=now)
        st["pending"].pop(req_id, None)
        save_state(st)
        send(user_id, DESK_GRANTED.format(link=link))
        return "Desk debloque, lien envoye."

    return "Decision inconnue."


def handle_callback(st, cq):
    """Tap d'Alan sur un bouton de carte (validation Tableau ou deblocage Desk)."""
    from_id = cq.get("from", {}).get("id")
    data = cq.get("data", "")
    cq_id = cq.get("id")
    msg = cq.get("message", {})

    if str(from_id) != str(ADMIN_CHAT_ID):
        tg("answerCallbackQuery", callback_query_id=cq_id, text="Reserve a l'admin.")
        return

    try:
        action, req_id = data.split(":", 1)
    except ValueError:
        tg("answerCallbackQuery", callback_query_id=cq_id)
        return

    result = apply_decision(st, req_id, action)
    tg("answerCallbackQuery", callback_query_id=cq_id, text=result or "OK")
    # Trace la decision sur la carte (retire les boutons)
    if msg:
        new_txt = (msg.get("text") or "") + f"\n\n→ {result}"
        tg("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
           text=new_txt)


# ----------------------------------------------------------------------
# Boucle principale (long-polling)
# ----------------------------------------------------------------------
def main():
    if not BOT_TOKEN:
        _log("ACCESS_BOT_TOKEN manquant : je m'arrete. (configure la variable d'env)")
        return
    st = load_state()
    _log(f"Bot d'acces demarre. offset={st['offset']} membres={len(st['members'])} "
         f"TG1={'OK' if TG1_CHAT_ID else 'manquant'} TG2={'OK' if TG2_CHAT_ID else 'manquant'}")

    while True:
        res = tg("getUpdates", offset=st["offset"] + 1, timeout=POLL_TIMEOUT)
        if not res.get("ok"):
            time.sleep(3)
            continue
        for upd in res.get("result", []):
            st["offset"] = upd["update_id"]
            try:
                if "message" in upd:
                    handle_message(st, upd["message"])
                elif "callback_query" in upd:
                    handle_callback(st, upd["callback_query"])
            except Exception as e:
                _log(f"  erreur traitement update {upd.get('update_id')}: {e}")
            save_state(st)   # persiste l'offset au fil de l'eau


if __name__ == "__main__":
    main()
