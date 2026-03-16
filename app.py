# RistoCost — Web App
# © 2025 Andrea Marella — Tutti i diritti riservati
# Backend: Flask + Supabase

from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import copy
from datetime import datetime
import csv
import io
import urllib.request
import urllib.error

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

app = Flask(__name__)

# ── SUPABASE CONFIG ───────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vyhfctuyndrliskrhiev.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ5aGZjdHV5bmRybGlza3JoaWV2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2NzYyMjksImV4cCI6MjA4OTI1MjIyOX0._pRj07j68yYV955dY08J7kpYlRkNiTpuOXt3whmzQ7I")
TABLE = "ristocost_data"
ROW_ID = "main"

def _sb_request(method, endpoint, body=None):
    """Chiamata HTTP a Supabase REST API"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"Supabase error {e.code}: {e.read().decode()}")
        return None

# ── DATI ─────────────────────────────────────────────────────────

def load_data():
    """Carica dati da Supabase, fallback su file locale"""
    try:
        rows = _sb_request("GET", f"{TABLE}?id=eq.{ROW_ID}&select=*")
        if rows and len(rows) > 0:
            row = rows[0]
            return {
                "ingredienti": row.get("ingredienti") or {},
                "ricette": row.get("ricette") or {},
                "storico_prezzi": row.get("storico_prezzi") or {}
            }
    except Exception as e:
        print(f"Supabase load error: {e}")
    # Fallback file locale
    base = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(base, "data.json")
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"ingredienti": {}, "ricette": {}, "storico_prezzi": {}}

def save_data(data):
    """Salva dati su Supabase"""
    data["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = {
        "id": ROW_ID,
        "ingredienti": data.get("ingredienti", {}),
        "ricette": data.get("ricette", {}),
        "storico_prezzi": data.get("storico_prezzi", {}),
        "last_update": data["last_update"]
    }
    try:
        # Upsert — inserisce o aggiorna
        _sb_request("POST", f"{TABLE}?on_conflict=id", body)
    except Exception as e:
        print(f"Supabase save error: {e}")

# ── ROUTES PRINCIPALI ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(load_data())

# ── INGREDIENTI ───────────────────────────────────────────────────

@app.route('/api/ingredienti', methods=['POST'])
def aggiungi_ingrediente():
    d = load_data()
    body = request.json
    nome = body.get('nome','').strip()
    if not nome:
        return jsonify({"error": "Nome obbligatorio"}), 400
    try:
        costo = float(body['costo'])
        quantita = float(body['quantita'])
        scarto = float(body.get('scarto', 0))
    except:
        return jsonify({"error": "Valori numerici non validi"}), 400
    if costo <= 0 or quantita <= 0:
        return jsonify({"error": "Costo e quantità devono essere > 0"}), 400
    if not (0 <= scarto < 100):
        return jsonify({"error": "Scarto deve essere tra 0 e 99"}), 400
    fattore = 1 / (1 - scarto / 100) if scarto < 100 else 1
    d['ingredienti'][nome] = {
        "costo_unitario": (costo / quantita) * fattore,
        "costo_unitario_lordo": costo / quantita,
        "unita": body.get('unita', 'g'),
        "quantita_totale": quantita,
        "costo_totale": costo,
        "scarto": scarto
    }
    save_data(d)
    return jsonify({"ok": True, "ingredienti": d['ingredienti']})

@app.route('/api/ingredienti/<nome>', methods=['PUT'])
def modifica_ingrediente(nome):
    d = load_data()
    if nome not in d['ingredienti']:
        return jsonify({"error": "Ingrediente non trovato"}), 404
    body = request.json
    nuovo_nome = body.get('nome', nome).strip()
    try:
        costo = float(body['costo'])
        quantita = float(body['quantita'])
        scarto = float(body.get('scarto', 0))
    except:
        return jsonify({"error": "Valori non validi"}), 400
    fattore = 1 / (1 - scarto / 100) if scarto < 100 else 1
    nu = (costo / quantita) * fattore
    info = d['ingredienti'][nome]
    if abs(nu - info.get('costo_unitario', 0)) > 0.000001:
        if nome not in d['storico_prezzi']:
            d['storico_prezzi'][nome] = []
        d['storico_prezzi'][nome].append({
            "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "costo_unitario": info['costo_unitario'],
            "unita": info['unita'], "note": "Modifica"
        })
    if nome != nuovo_nome:
        del d['ingredienti'][nome]
    d['ingredienti'][nuovo_nome] = {
        "costo_unitario": nu,
        "costo_unitario_lordo": costo / quantita,
        "unita": body.get('unita', info['unita']),
        "quantita_totale": quantita,
        "costo_totale": costo,
        "scarto": scarto
    }
    save_data(d)
    return jsonify({"ok": True, "ingredienti": d['ingredienti']})

@app.route('/api/ingredienti/<nome>', methods=['DELETE'])
def elimina_ingrediente(nome):
    d = load_data()
    if nome not in d['ingredienti']:
        return jsonify({"error": "Non trovato"}), 404
    del d['ingredienti'][nome]
    save_data(d)
    return jsonify({"ok": True, "ingredienti": d['ingredienti']})

@app.route('/api/storico/<nome>', methods=['GET'])
def storico_prezzi(nome):
    d = load_data()
    return jsonify(d.get('storico_prezzi', {}).get(nome, []))

# ── RICETTE ───────────────────────────────────────────────────────

@app.route('/api/ricette', methods=['POST'])
def salva_ricetta():
    d = load_data()
    body = request.json
    nome = body.get('nome','').strip()
    if not nome:
        return jsonify({"error": "Nome obbligatorio"}), 400
    d['ricette'][nome] = {
        "ingredienti": body.get('ingredienti', {}),
        "margine": float(body.get('margine', 30)),
        "porzioni": int(body.get('porzioni', 1)),
        "note": body.get('note', ''),
        "data_creazione": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_data(d)
    return jsonify({"ok": True, "ricette": d['ricette']})

@app.route('/api/ricette/<nome>', methods=['DELETE'])
def elimina_ricetta(nome):
    d = load_data()
    if nome not in d['ricette']:
        return jsonify({"error": "Non trovata"}), 404
    del d['ricette'][nome]
    save_data(d)
    return jsonify({"ok": True, "ricette": d['ricette']})

@app.route('/api/ricette/<nome>/duplica', methods=['POST'])
def duplica_ricetta(nome):
    d = load_data()
    if nome not in d['ricette']:
        return jsonify({"error": "Non trovata"}), 404
    nuovo_nome = request.json.get('nuovo_nome','').strip()
    if not nuovo_nome:
        return jsonify({"error": "Nome copia obbligatorio"}), 400
    if nuovo_nome in d['ricette']:
        return jsonify({"error": f"'{nuovo_nome}' esiste già"}), 400
    d['ricette'][nuovo_nome] = copy.deepcopy(d['ricette'][nome])
    d['ricette'][nuovo_nome]['data_creazione'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_data(d)
    return jsonify({"ok": True, "ricette": d['ricette']})

# ── PDF ───────────────────────────────────────────────────────────

@app.route('/api/pdf/ricetta', methods=['POST'])
def esporta_pdf_ricetta():
    if not REPORTLAB_OK:
        return jsonify({"error": "reportlab non installato"}), 500
    body = request.json
    nome = body.get('nome','Ricetta')
    ingredienti_ricetta = body.get('ingredienti', {})
    margine = float(body.get('margine', 30))
    iva = float(body.get('iva', 0))
    porzioni = max(1, int(body.get('porzioni', 1)))
    note = body.get('note','')
    d = load_data()

    totale = sum(d['ingredienti'][ing]['costo_unitario'] * q
                 for ing, q in ingredienti_ricetta.items() if ing in d['ingredienti'])
    prezzo = totale * (1 + margine / 100)
    profitto = prezzo - totale
    con_iva = prezzo * (1 + iva / 100)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('T', parent=styles['Title'], fontSize=20,
                                 textColor=colors.HexColor('#2c3e50'), spaceAfter=6)
    sub_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=10,
                               textColor=colors.grey, alignment=TA_CENTER)
    elements.append(Paragraph("Scheda Tecnica di Produzione", title_style))
    elements.append(Paragraph(nome, sub_style))
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                               ParagraphStyle('D', parent=styles['Normal'], fontSize=9,
                                              textColor=colors.grey, alignment=TA_RIGHT)))
    elements.append(HRFlowable(width="100%", thickness=2,
                               color=colors.HexColor('#2c3e50'), spaceAfter=12))

    h = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12,
                        textColor=colors.HexColor('#1976D2'), spaceBefore=10, spaceAfter=6)

    info_rows = [["Porzioni", str(porzioni)], ["Margine", f"{margine:.1f}%"]]
    if note: info_rows.append(["Note", note])
    ti = Table(info_rows, colWidths=[4*cm, 13*cm])
    ti.setStyle(TableStyle([('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white,colors.HexColor('#f5f5f5')]),
        ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#cccccc')),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    elements.append(ti); elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph("Ingredienti e Costi", h))
    data = [["Ingrediente","Quantità","Costo (€)","% sul totale"]]
    for ing, q in ingredienti_ricetta.items():
        if ing in d['ingredienti']:
            info = d['ingredienti'][ing]
            c = info['costo_unitario'] * q
            perc = f"{c/totale*100:.1f}%" if totale > 0 else "0%"
            data.append([ing, f"{q} {info['unita']}", f"€{c:.2f}", perc])
    data.append(["TOTALE","",f"€{totale:.2f}","100%"])
    t = Table(data, colWidths=[6.5*cm,3.5*cm,3.5*cm,3.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#2c3e50')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),9),('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(0,0),(0,-1),'LEFT'),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#f5f5f5')]),
        ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e3f2fd')),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#cccccc')),
        ('ROWHEIGHT',(0,0),(-1,-1),20),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    elements.append(t); elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph("Analisi Costi", h))
    costi = [["Costo di Produzione",f"€{totale:.2f}"],
             ["Costo per Porzione",f"€{totale/porzioni:.2f}"],
             ["Margine di Profitto",f"{margine:.1f}%"],
             ["Prezzo di Vendita",f"€{prezzo:.2f}"],
             ["Profitto Unitario",f"€{profitto:.2f}"]]
    if iva > 0: costi.append([f"Prezzo con IVA ({iva:.0f}%)",f"€{con_iva:.2f}"])
    tc = Table(costi, colWidths=[9*cm,4*cm])
    tc.setStyle(TableStyle([('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTSIZE',(0,0),(-1,-1),9),
        ('FONTNAME',(0,3),(-1,3),'Helvetica-Bold'),('TEXTCOLOR',(0,3),(-1,3),colors.HexColor('#1976D2')),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white,colors.HexColor('#f5f5f5')]),
        ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#cccccc')),
        ('ROWHEIGHT',(0,0),(-1,-1),20),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    elements.append(tc)

    doc.build(elements)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=True, download_name=f"{nome}_ricetta.pdf")


@app.route('/api/pdf/report', methods=['GET'])
def report_mensile():
    if not REPORTLAB_OK:
        return jsonify({"error": "reportlab non installato"}), 500
    d = load_data()
    if not d['ricette']:
        return jsonify({"error": "Nessuna ricetta salvata"}), 400

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet(); elements = []
    mese = datetime.now().strftime("%B %Y").capitalize()
    title_s = ParagraphStyle('T', parent=styles['Title'], fontSize=20,
                              textColor=colors.HexColor('#2c3e50'), spaceAfter=6)
    elements.append(Paragraph(f"Report Mensile — {mese}", title_s))
    elements.append(Paragraph(f"{len(d['ricette'])} ricette · {len(d['ingredienti'])} ingredienti",
                               ParagraphStyle('S', parent=styles['Normal'], fontSize=10,
                                              textColor=colors.grey, alignment=TA_CENTER)))
    elements.append(HRFlowable(width="100%", thickness=2,
                               color=colors.HexColor('#2c3e50'), spaceAfter=12))
    h = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12,
                        textColor=colors.HexColor('#1976D2'), spaceBefore=12, spaceAfter=6)
    elements.append(Paragraph("Riepilogo Ricette", h))
    rows = [["Ricetta","Porz.","Costo prod.","x porz.","Prezzo","Profitto","Margine"]]
    tc = tp = 0.0
    for nome_r, r in sorted(d['ricette'].items()):
        mg = r.get('margine', 30); porzioni = max(1, r.get('porzioni', 1))
        costo = sum(d['ingredienti'][ing]['costo_unitario']*q
                    for ing,q in r['ingredienti'].items() if ing in d['ingredienti'])
        prezzo = costo*(1+mg/100); profitto = prezzo-costo; tc+=costo; tp+=profitto
        rows.append([nome_r, str(porzioni), f"€{costo:.2f}", f"€{costo/porzioni:.2f}",
                     f"€{prezzo:.2f}", f"€{profitto:.2f}", f"{mg:.0f}%"])
    rows.append(["TOTALE","",f"€{tc:.2f}","","",f"€{tp:.2f}",""])
    t = Table(rows, colWidths=[4.5*cm,1.5*cm,2.5*cm,2.5*cm,2.8*cm,2.5*cm,1.9*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#2c3e50')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(1,0),(-1,-1),'RIGHT'),('ALIGN',(0,0),(0,-1),'LEFT'),
        ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#f5f5f5')]),
        ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e3f2fd')),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#cccccc')),
        ('ROWHEIGHT',(0,0),(-1,-1),18),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=True, download_name=f"report_{datetime.now().strftime('%Y_%m')}.pdf")


# ── BACKUP ────────────────────────────────────────────────────────

@app.route('/api/backup', methods=['GET'])
def lista_backup():
    """Con Supabase i backup sono gestiti internamente — restituisce info ultimo salvataggio"""
    try:
        rows = _sb_request("GET", f"{TABLE}?id=eq.{ROW_ID}&select=last_update")
        if rows and rows[0].get("last_update"):
            return jsonify([f"Ultimo salvataggio: {rows[0]['last_update']}"])
    except:
        pass
    return jsonify([])

@app.route('/api/backup/<fname>/ripristina', methods=['POST'])
def ripristina_backup(fname):
    return jsonify({"ok": True, "data": load_data()})

@app.route('/api/backup/<fname>', methods=['DELETE'])
def elimina_backup(fname):
    return jsonify({"ok": True})

# ── IMPORTA CSV ───────────────────────────────────────────────────

@app.route('/api/importa', methods=['POST'])
def importa_ingredienti():
    if 'file' not in request.files:
        return jsonify({"error": "Nessun file"}), 400
    f = request.files['file']
    d = load_data(); importati = 0
    try:
        stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        for row in reader:
            def get_col(*keys):
                for k in keys:
                    for ck, cv in row.items():
                        if k in ck.lower(): return cv
                return None
            nome = get_col("nome","name")
            costo_s = get_col("costo","cost","prezzo","price")
            qta_s = get_col("quant")
            unita = get_col("unit","misura") or "g"
            if not nome or not costo_s or not qta_s: continue
            try:
                costo = float(str(costo_s).replace(',','.'))
                qta = float(str(qta_s).replace(',','.'))
            except: continue
            if costo > 0 and qta > 0:
                d['ingredienti'][nome.strip()] = {
                    "costo_unitario": costo/qta, "costo_unitario_lordo": costo/qta,
                    "unita": unita.strip(), "quantita_totale": qta,
                    "costo_totale": costo, "scarto": 0
                }
                importati += 1
        save_data(d)
        return jsonify({"ok": True, "importati": importati, "ingredienti": d['ingredienti']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
