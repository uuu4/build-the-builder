"""Python bodies for the code nodes of the statement-debt agent (prefixed by pycode.with_params)."""

COMMON = r'''
ONES = ['', 'bir', 'iki', 'üç', 'dört', 'beş', 'altı', 'yedi', 'sekiz', 'dokuz']
TENS = ['', 'on', 'yirmi', 'otuz', 'kırk', 'elli', 'altmış', 'yetmiş', 'seksen', 'doksan']
DIG = ['sıfır', 'bir', 'iki', 'üç', 'dört', 'beş', 'altı', 'yedi', 'sekiz', 'dokuz']
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
def w3(n):
    h, r = divmod(n, 100)
    t, o = divmod(r, 10)
    s = []
    if h:
        s.append(('' if h == 1 else ONES[h] + ' ') + 'yüz')
    if t:
        s.append(TENS[t])
    if o:
        s.append(ONES[o])
    return ' '.join(s)
def words(n):
    n = int(n)
    if n == 0:
        return 'sıfır'
    parts = []
    for val, name in ((10**9, 'milyar'), (10**6, 'milyon'), (1000, 'bin')):
        q, n = divmod(n, val)
        if q:
            if val == 1000 and q == 1:
                parts.append('bin')
            else:
                parts.append(w3(q) + ' ' + name)
    if n:
        parts.append(w3(n))
    return ' '.join(parts)
def split(x):
    c = int(round(abs(num(x)) * 100))
    return c // 100, c % 100
CUR = dict(TL=('Türk Lirası', 'lira', 'kuruş'), USD=('Dolar', 'dolar', 'sent'), EUR=('Euro', 'euro', 'sent'), GBP=('İngiliz Sterlini', 'sterlin', 'peni'))
def amt(x, cur):
    full, unit, sub = CUR[cur]
    a, b = split(x)
    if b == 0:
        return words(a) + ' ' + (full if cur == 'TL' else unit)
    return words(a) + ' ' + unit + ' ' + words(b) + ' ' + sub
def dir_(w):
    w = w.strip()
    m = re.search(r'(\d+)$', w)
    base = words(int(m.group(1))) if m else w
    vs = [ch for ch in base.lower() if ch in 'aıeioöuü']
    v = vs[-1] if vs else 'e'
    hv = dict(a='ı', ı='ı', e='i', i='i', o='u', u='u', ö='ü', ü='ü')[v]
    c = 't' if base[-1].lower() in 'fstkçşhp' else 'd'
    ap = "'" if (m or w.split()[-1][:1].isupper()) else ''
    return w + ap + c + hv + 'r'
def pdate(s):
    try:
        d, m, y = str(s).strip().split('.')
        return datetime.date(int(y), int(m), int(d))
    except Exception:
        return None
def sdate(d):
    return str(d.day) + ' ' + AYLAR[d.month - 1] + ' ' + str(d.year)
def digits_say(s):
    return ' '.join(DIG[int(ch)] for ch in str(s) if ch.isdigit())
def norm(s):
    s = str(s or '')
    for a, b in (('İ', 'i'), ('I', 'ı')):
        s = s.replace(a, b)
    s = s.lower()
    for a, b in (('ı', 'i'), ('ş', 's'), ('ğ', 'g'), ('ü', 'u'), ('ö', 'o'), ('ç', 'c')):
        s = s.replace(a, b)
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', s).split())
def _walk(o, path):
    for p in path.split('.'):
        if isinstance(o, str):
            try:
                o = json.loads(o)
            except Exception:
                return None
        if isinstance(o, dict):
            o = o.get(p)
        else:
            return None
    return o
def resp(node, path):
    for k in (node + '_response.data.' + path, node + '_response.' + path):
        v = vars.get(k)
        if v is not None and str(v) != '':
            return v
    for root, sub in ((node + '_response', 'data.' + path), (node + '_response.data', path)):
        if root in vars:
            v = _walk(vars.get(root), sub)
            if v is not None and not isinstance(v, (dict, list)):
                return v
    return None
def has_block(node, path):
    pre = node + '_response.data.' + path + '.'
    if any(str(k).startswith(pre) for k in vars):
        return True
    for root, sub in ((node + '_response', 'data.' + path), (node + '_response.data', path)):
        if root in vars and isinstance(_walk(vars.get(root), sub), dict):
            return True
    return False
def rc_ok(node):
    return str(resp(node, 'result.returnCode') or '') == '1'
def any_code(node, code):
    for k, v in list(vars.items()):
        if str(k).startswith(node + '_') and code in str(v):
            return True
    return False
def load_cards():
    try:
        return json.loads(vars.get('cards_json') or '[]')
    except Exception:
        return []
def card_examples(cs):
    names = []
    for c in cs:
        n = c['name'] or ('sonu ' + digits_say(c['last4']) + ' ile biten kartınız')
        if n not in names:
            names.append(n)
    return names
def join_ve(xs):
    xs = list(xs)
    if len(xs) <= 1:
        return ''.join(xs)
    return ', '.join(xs[:-1]) + ' ve ' + xs[-1]
def join_veya(xs):
    xs = list(xs)
    if len(xs) <= 1:
        return ''.join(xs)
    return ', '.join(xs[:-1]) + ' veya ' + xs[-1]
def select(c):
    vars['sel_num'] = c['num']
    vars['sel_last4'] = c['last4']
    vars['sel_name'] = c['name']
'''

CARDS = r'''
try:
    vars['cards_state'] = 'error'
    if rc_ok('get_cards'):
        raw = read_list('get_cards', 'data.cards')
        if not raw:
            raw = _walk(vars.get('get_cards_response'), 'data.data.cards') or _walk(vars.get('get_cards_response.data'), 'data.cards') or []
        cs = []
        for c in raw:
            numb = str(c.get('cardNumber') or '')
            l4 = str(c.get('cardNumberLast4') or '') or numb[-4:]
            main = str(c.get('isMainCard')).lower() != 'false'
            cs.append(dict(num=numb, last4=l4, name=str(c.get('productName') or '').strip(), main=main))
        vars['cards_json'] = json.dumps(cs)
        vars['card_count'] = str(len(cs))
        mains = [c for c in cs if c['main']]
        if not cs:
            vars['cards_state'] = 'none'
        elif len(cs) == 1:
            select(cs[0])
            vars['cards_state'] = 'one' if cs[0]['main'] else 'none'
        else:
            ex = card_examples(mains or cs)[:2]
            vars['card_prompt'] = 'Hangi kartınızın borcunu öğrenmek istersiniz? Örneğin, ' + join_veya(ex) + ' diyebilirsiniz.'
            vars['cand_json'] = json.dumps(list(range(len(cs))))
            vars['pick_tries'] = '0'
            vars['cards_state'] = 'many'
    elif any_code('get_cards', 'FB_IVR_CHANNEL_102') or str(vars.get('get_cards_status_code') or '') == '404':
        vars['cards_state'] = 'none'
except Exception as e:
    vars['cards_state'] = 'error'
'''

RESET_PICK = r'''
cs = load_cards()
mains = [c for c in cs if c['main']]
ex = card_examples(mains or cs)[:2]
vars['card_prompt'] = 'Hangi kartınızın borcunu öğrenmek istersiniz? Örneğin, ' + join_veya(ex) + ' diyebilirsiniz.'
vars['cand_json'] = json.dumps(list(range(len(cs))))
vars['pick_tries'] = '0'
vars['pick_kind'] = ''
vars['pick_text'] = ''
'''

MATCH = r'''
try:
    cs = load_cards()
    cand = json.loads(vars.get('cand_json') or '[]') or list(range(len(cs)))
    kind = str(vars.get('pick_kind') or '')
    text = str(vars.get('pick_text') or '')
    tries = int(num(vars.get('pick_tries'), 0))
    vars['pick_kind'] = ''
    vars['pick_text'] = ''
    base_q = 'Hangi kartınızın borcunu öğrenmek istersiniz? Örneğin, ' + join_veya(card_examples([cs[i] for i in cand])[:2]) + ' diyebilirsiniz.'
    res = 'ask'
    msg = base_q
    if kind == 'repeat':
        msg = vars.get('card_prompt') or base_q
    else:
        digs = re.sub(r'\D', '', text)
        hits = None
        if kind == 'card' and digs and len(digs) >= 4:
            if len(digs) >= 6:
                hits = [i for i in cand if re.sub(r'\D', '', cs[i]['num']).endswith(digs[-6:]) and '*' not in cs[i]['num'][-6:]]
                if not hits:
                    hits = [i for i in cand if cs[i]['last4'] == digs[-4:]]
                    if len(hits) > 1 and len(digs) >= 6:
                        hits = hits
            else:
                hits = [i for i in cand if cs[i]['last4'] == digs[-4:]]
            if len(digs) >= 16:
                full = [i for i in cand if re.sub(r'\D', '', cs[i]['num']) == digs[-16:]]
                if full:
                    hits = full
            if not hits:
                tries += 1
                msg = 'Bu numarayla eşleşen bir kartınız bulunmuyor. ' + base_q
            elif len(hits) == 1:
                res = 'match'
            else:
                cand = hits
                if len(digs) >= 6:
                    msg = 'Son altı hanesi aynı olan birden fazla kartınız var. Kart numaranızı söyler misiniz?'
                else:
                    msg = 'Son dört hanesi ' + digs[-4:] + ' olan birden fazla kartınız var. Kartınızın son altı hanesini söyler misiniz?'
        elif kind == 'card' and norm(text):
            t = norm(text)
            hits = [i for i in cand if cs[i]['name'] and (t in norm(cs[i]['name']) or norm(cs[i]['name']) in t)]
            if not hits:
                toks = [x for x in t.split() if len(x) > 2]
                hits = [i for i in cand if cs[i]['name'] and any(x in norm(cs[i]['name']).split() for x in toks)]
            if not hits:
                tries += 1
                allc = list(range(len(cs)))
                cand = allc
                msg = 'Bu isimde bir kartınız bulunmuyor. Kartlarınız: ' + join_ve(card_examples(cs)) + '. Hangisinin borcunu öğrenmek istersiniz?'
            elif len(hits) == 1:
                res = 'match'
            else:
                cand = hits
                names = card_examples([cs[i] for i in hits])
                if len(names) == 1:
                    msg = names[0] + ' isimli birden fazla kartınız var. Kartınızın son dört hanesini söyler misiniz?'
                else:
                    msg = join_veya(names) + ' kartlarınızdan hangisini kastediyorsunuz?'
        elif kind == 'all':
            tries += 1
            msg = 'Borç bilgisini tek tek kart için verebiliyorum. ' + base_q
        else:
            tries += 1
            msg = base_q
        if res == 'match':
            c = cs[hits[0]]
            if not c['main']:
                res = 'ask'
                cand = [i for i in range(len(cs)) if cs[i]['main']] or list(range(len(cs)))
                msg = 'Bu kart için borç bilgisi verebileceğim uygun bir kart bulunmuyor. Lütfen başka bir kartınızı seçin.'
            else:
                select(c)
    if res != 'match' and tries >= 3:
        res = 'tries'
    vars['pick_tries'] = str(tries)
    vars['cand_json'] = json.dumps(cand)
    vars['card_prompt'] = msg
    vars['match_state'] = res
except Exception as e:
    vars['match_state'] = 'tries'
'''

READING = r'''
try:
    vars['reading_state'] = 'error'
    vars['ar_kind'] = ''
    vars['of_kind'] = ''
    if rc_ok('get_balance'):
        b = lambda p: resp('get_balance', 'data.' + p)
        today = get_now().date()
        l4 = vars.get('sel_last4') or str(b('cardNumberLast4') or '')
        name = vars.get('sel_name') or str(b('productName') or '').strip()
        intro = 'Sonu ' + digits_say(l4) + ' ile biten ' + (name + ' kartınıza' if name else 'kartınıza')
        sd = pdate(b('statementDate'))
        dd = pdate(b('lastPayDate'))
        vars['stmt_date'] = str(b('statementDate') or '')
        present = []
        for cur in ('TL', 'USD', 'EUR', 'GBP'):
            if has_block('get_balance', 'data.debt' + cur):
                present.append(cur)
        def f(cur, fld):
            return num(b('debt' + cur + '.' + fld))
        has = [c for c in present if f(c, 'remainingDebt') > 0.004]
        clear = [c for c in present if c not in has]
        vars['pdf_currency'] = has[0] if has else 'TL'
        parts = []
        status = str(b('statementPaymentStatus') or '')
        if sd is None:
            parts.append(intro + ' kesilmiş bir ekstre bulunmadığı için ekstre borcunuz bulunmamaktadır.')
        elif status == 'NO_DEBT' or not has:
            g = f('TL', 'totalDebt')
            s = intro.replace('kartınıza', 'kartınızın') + ' ' + sdate(sd) + ' tarihli ekstresinden borcunuz bulunmamaktadır.'
            if g > 0.004:
                s += ' Gelecek dönemler dahil toplam borcunuz ' + dir_(amt(g, 'TL')) + '.'
            if dd:
                s += ' Son ödeme tarihiniz ' + ('bugün' if dd == today else sdate(dd)) + ' olacaktır.'
            parts.append(s)
            vars['nodebt'] = '1'
        else:
            vars['nodebt'] = '0'
            if sd == today:
                parts.append('Hesap kesim tarihiniz bugün, ekstreniz saat 00.00 itibarıyla kesilecek.')
            first = True
            for cur in has:
                full = CUR[cur][0]
                sx, mn, rd, rm = f(cur, 'statementDebt'), f(cur, 'minPayment'), f(cur, 'remainingDebt'), f(cur, 'remainingMinPayment')
                if cur == 'TL':
                    if rm > 0.004 and rm >= mn - 0.004:
                        s = 'Türk Lirası borcunuz ' + amt(sx, cur) + ', ödenmesi gereken minimum tutar ' + dir_(amt(mn, cur)) + '.'
                    elif rm <= 0.004:
                        s = 'Türk Lirası borcunuz ' + amt(sx, cur) + ', kalan toplam borcunuz ' + dir_(amt(rd, cur)) + '. Minimum ödemenizi yaptığınız için teşekkür ederiz.'
                    else:
                        s = ('Türk Lirası borcunuz ' + amt(sx, cur) + ', ödenmesi gereken minimum tutar ' + amt(mn, cur) + ', kalan toplam borcunuz '
                             + amt(rd, cur) + ', kalan minimum ödeme tutarınız ' + dir_(amt(rm, cur)) + '.')
                else:
                    s = full + ' borcunuz ' + amt(sx, cur) + ', kalan toplam borcunuz ' + amt(rd, cur) + ', ödenmesi gereken minimum tutar ' + dir_(amt(mn, cur)) + '.'
                if first:
                    s = intro + ' ait ' + sdate(sd) + ' tarihinde kesilen ekstre ' + s
                    first = False
                parts.append(s)
            if clear:
                parts.append(join_ve([CUR[c][0] for c in clear]) + ' borcunuz bulunmamaktadır.')
            ap = str(b('automaticPaymentFlag') or '')
            rem = f('TL', 'remainAutomaticPaymentAmount')
            if dd and today > dd and ap == 'Y' and rem > 0.004:
                parts.append('Otomatik ödeme talimatınızdan tahsil edilecek kalan tutar ' + dir_(amt(rem, 'TL')) + '.')
            if dd:
                if dd == today:
                    parts.append('Borçlarınız için son ödeme tarihiniz bugündür.')
                elif today > dd:
                    parts.append(sdate(dd) + ' olan son ödeme tarihiniz geçmiştir. Gelecek dönemler dahil toplam Türk Lirası borcunuz ' + dir_(amt(f('TL', 'totalDebt'), 'TL')) + '.')
                else:
                    parts.append('Borçlarınız için son ödeme tarihiniz ' + dir_(sdate(dd)) + '.')
        vars['reading_text'] = ' '.join(parts)
        vars['reading_state'] = 'ok'
except Exception as e:
    vars['reading_state'] = 'error'
'''

OFFER = r'''
try:
    vars['ar_kind'] = ''
    vars['of_kind'] = ''
    email = ''
    vars['email_state'] = 'error'
    if rc_ok('get_email'):
        e = str(resp('get_email', 'data.ibanEmail') or '').strip()
        ct = str(resp('get_email', 'data.communicationType') or '')
        email = e if (e and '@' in e and ct != 'Phone') else ''
        vars['email_state'] = 'ok'
    vars['email_addr'] = email
    vars['has_email'] = '1' if email else '0'
    if email:
        local, dom = email.split('@', 1)
        if len(email) <= 32 and re.match(r'^[A-Za-z.]+$', local):
            vars['email_say'] = email
        else:
            vars['email_say'] = local[0].lower() + ' ile başlayan ' + dom.split('.')[0].capitalize() + ' adresiniz'
    if email:
        offer = 'Hesap kesim tarihinizi değiştirebilirim ya da ekstrenizi kayıtlı mail adresinize gönderebilirim.'
    else:
        offer = 'Hesap kesim tarihinizi değiştirebilirim.'
    vars['offer_text'] = offer
    many = int(num(vars.get('card_count'), 1)) > 1
    if many:
        vars['ar_stage'] = 'another'
        vars['followup_q'] = 'Başka bir kartınızın borcunu öğrenmek ister misiniz?'
    elif vars.get('nodebt') == '1':
        vars['ar_stage'] = 'end'
        vars['followup_q'] = ''
    else:
        vars['ar_stage'] = 'offer'
        vars['followup_q'] = offer
    vars['offer_state'] = 'ok'
except Exception as e:
    vars['offer_state'] = 'error'
'''

PDF = r'''
vars['pdf_state'] = 'ok' if (rc_ok('send_pdf') and str(resp('send_pdf', 'data.exitState') or '').upper() == 'DONE') else 'fail'
n = int(num(vars.get('pdf_sends'), 0)) + 1
vars['pdf_sends'] = str(n)
vars['em_ans'] = ''
'''

WEEK = r'''
try:
    vars['week_state'] = 'error'
    vars['wk_ans'] = ''
    vars['wk_num'] = ''
    if rc_ok('get_week'):
        w = lambda p: resp('get_week', 'data.' + p)
        cw = int(num(w('statementWeek'), 0))
        vars['cur_week'] = str(cw)
        vars['cur_day'] = str(int(num(w('statementDay'), 0)))
        name = vars.get('sel_name') or str(w('productName') or '')
        ns, nd = pdate(w('nextStatementDate')), pdate(w('nextLastPayDate'))
        rel = str(w('relationType') or '').strip().upper()
        other = str(w('relatedCardProductName') or '').strip()
        ol4 = str(w('relatedCardNumber') or '')[-4:]
        txt = (name + ' kartınızın' if name else 'Kartınızın') + ' hesap kesim tarihi her ayın ' + str(cw) + '. haftası olarak tanımlı. Bir sonraki hesap kesim tarihiniz ' + (sdate(ns) if ns else '') + ', son ödeme tarihiniz ' + (sdate(nd) if nd else '') + '.'
        joint = ''
        if rel in ('M', 'C'):
            txt = ('Sonu ' + digits_say(vars.get('sel_last4')) + ' ile biten ' + name + ' kartınız ile sonu ' + digits_say(ol4) + ' ile biten ' + other
                   + ' kartınız aynı ekstreyi paylaşıyor. ' + txt + ' Bu tarihler iki kartınız için de geçerlidir.')
            if rel == 'M':
                joint = 'Bu değişiklik kartınıza bağlı ' + other + ' kartınızı da etkileyecek. '
            else:
                joint = 'Bu değişiklik kartınızın bağlı olduğu ' + other + ' kartınızı da etkileyecek. '
        vars['joint_note'] = joint
        vars['week_text'] = txt
        opts = [str(i) + '.' for i in (1, 2, 3, 4) if i != cw]
        vars['week_options'] = ', '.join(opts[:-1]) + ' ya da ' + opts[-1]
        vars['week_prompt'] = 'Hesap kesim tarihinizi ayın ' + vars['week_options'] + ' haftasına alabilirim. Hangisini tercih edersiniz?'
        vars['wp_tries'] = '0'
        vars['week_state'] = 'ok'
        pw = str(vars.get('want_week') or '').strip().rstrip('.')
        vars['want_week'] = ''
        if pw in ('1', '2', '3', '4') and pw != str(cw):
            vars['wk_num'] = pw
            vars['week_state'] = 'preset'
except Exception as e:
    vars['week_state'] = 'error'
'''

WEEK_PICK = r'''
c = str(vars.get('wk_num') or vars.get('wp_num') or '').strip().rstrip('.')
vars['wk_num'] = ''
vars['wp_num'] = ''
vars['wp_kind'] = ''
t = int(num(vars.get('wp_tries'), 0))
if c in ('1', '2', '3', '4') and c != vars.get('cur_week'):
    vars['new_week'] = c
    vars['wpick_state'] = 'ok'
elif c == vars.get('cur_week'):
    vars['week_prompt'] = 'Kartınızın hesap kesim tarihi zaten ayın ' + c + '. haftasında, bir değişiklik gerekmiyor. Hesap kesim tarihinizi ayın ' + vars.get('week_options', '') + ' haftasına alabilirim. Hangisini tercih edersiniz?'
    vars['wpick_state'] = 'ask'
    vars['wp_tries'] = str(t + 1)
else:
    vars['week_prompt'] = 'Hesap kesim tarihinizi ayın ' + vars.get('week_options', '') + ' haftasına alabilirim. Hangisini tercih edersiniz?'
    vars['wpick_state'] = 'ask'
    vars['wp_tries'] = str(t + 1)
if vars['wpick_state'] != 'ok' and t + 1 >= 3:
    vars['wpick_state'] = 'tries'
'''

DECIDE = r'''
try:
    vars['wc_ans'] = ''
    vars['decide_state'] = 'error'
    if rc_ok('decide_week'):
        a = pdate(resp('decide_week', 'data.statementDate'))
        b = pdate(resp('decide_week', 'data.statementDueDate'))
        if a and b:
            vars['new_stmt_say'] = sdate(a)
            vars['new_due_say'] = sdate(b)
            vars['confirm_text'] = (vars.get('joint_note') or '') + 'Yeni hesap kesim haftanız her ayın ' + vars['new_week'] + '. haftası olacak. Yeni hesap kesim tarihiniz ' + sdate(a) + ', son ödeme tarihiniz ' + sdate(b) + ' olacak. Onaylıyor musunuz?'
            name = vars.get('sel_name') or ''
            vars['done_text'] = ('Sonu ' + digits_say(vars.get('sel_last4')) + ' ile biten ' + (name + ' ' if name else '') + 'kartınızın hesap kesim haftası her ayın '
                                 + vars['new_week'] + '. haftası olarak değiştirildi. Yeni hesap kesim tarihiniz ' + sdate(a) + ', son ödeme tarihiniz ' + sdate(b) + '. Sizi ana menüye yönlendiriyorum.')
            vars['decide_state'] = 'ok'
except Exception as e:
    vars['decide_state'] = 'error'
'''

CHANGE = r'''
ok = rc_ok('change_week') and str(resp('change_week', 'data.exitState') or '').upper() == 'OK' and int(num(resp('change_week', 'data.responseCode'), -1)) == 0
vars['change_state'] = 'ok' if ok else 'fail'
'''
