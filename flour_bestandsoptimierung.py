#!/usr/bin/env python3
import os
import glob
import math
import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

BASE_DIR = os.getcwd()

def get_latest_file(pattern):
    search_path = os.path.join(BASE_DIR, pattern)
    files = glob.glob(search_path)
    return max(files, key=os.path.getmtime) if files else None

def get_dynamic_shops(sales_file):
    """Liest die verfügbaren Shops dynamisch aus der articlessold Datei."""
    if not sales_file: return []
    try:
        # Wir nutzen 'Lager' anstatt 'Kasse', da diese exakt mit den 
        # 'Bestand: [Shop]' Spalten in den Stammdaten übereinstimmt.
        df = pd.read_csv(sales_file, sep=';', encoding='ISO-8859-1', usecols=['Lager'])
        shops = [str(s).strip() for s in df['Lager'].dropna().unique() if str(s).strip()]
        return sorted(shops)
    except Exception:
        return []

def sanitize_filename(name):
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_")

def calculate_need(sales, min_stock, apply_buffer):
    buffered_sales = math.ceil(sales * 1.2) if apply_buffer else sales
    return max(buffered_sales, min_stock)

def distribute_surplus(surplus, target_sales):
    total = sum(target_sales.values())
    if total == 0: return {k: 0 for k in target_sales}
    shares = {k: (v / total) * surplus for k, v in target_sales.items()}
    distributed = {k: int(math.floor(v)) for k, v in shares.items()}
    remainder = int(surplus - sum(distributed.values()))
    sorted_rem = sorted(shares.keys(), key=lambda k: shares[k] - distributed[k], reverse=True)
    for i in range(remainder):
        distributed[sorted_rem[i]] += 1
    return distributed

def load_and_prep_data(sales_file, art_file):
    try:
        sales_df = pd.read_csv(sales_file, sep=';', encoding='ISO-8859-1', decimal=',')
        art_df = pd.read_csv(art_file, sep=';', encoding='ISO-8859-1', decimal=',')
        if sales_df.empty:
            sales_pivot = pd.DataFrame()
        else:
            sales_agg = sales_df.groupby(['Nummer', 'Lager'])['Menge'].sum().reset_index()
            sales_pivot = sales_agg.pivot(index='Nummer', columns='Lager', values='Menge').fillna(0)
        return True, sales_df, art_df, sales_pivot
    except Exception as e:
        return False, None, None, f"Fehler beim Lesen der Dateien: {e}"

# ==========================================
# LOGIK: BESTELLVORSCHLAG
# ==========================================
def build_order_data(mode, min_stock, apply_buffer, sales_file, art_file, shops):
    success, _, art_df, sales_pivot = load_and_prep_data(sales_file, art_file)
    if not success:
        return False, sales_pivot, None

    is_central = (mode == "Zentrale Bestellung")
    results = []

    for _, row in art_df.iterrows():
        art_no = str(row.get('Artikel-Nr', '')).strip()
        if not art_no or art_no == 'nan' or sales_pivot.empty or art_no not in sales_pivot.index:
            continue

        art_name = str(row.get('Bezeichnung', ''))
        lieferant = str(row.get('Einkauf Lieferant 0', '')).strip()
        hersteller = str(row.get('Hersteller', '')).strip()

        lieferant = lieferant if lieferant and lieferant != 'nan' else "Unbekannter Lieferant"
        hersteller = hersteller if hersteller and hersteller != 'nan' else "-"

        stock, sales = 0, 0
        if is_central:
            for shop in shops:
                stock += int(float(row.get(f'Bestand: {shop}', 0))) if pd.notnull(row.get(f'Bestand: {shop}')) else 0
                if shop in sales_pivot.columns:
                    sales += int(sales_pivot.at[art_no, shop])
        else:
            stock = int(float(row.get(f'Bestand: {mode}', 0))) if pd.notnull(row.get(f'Bestand: {mode}')) else 0
            if mode in sales_pivot.columns:
                sales = int(sales_pivot.at[art_no, mode])

        if stock == 0 and sales == 0:
            continue

        bedarf = calculate_need(sales, min_stock, apply_buffer)
        to_order = bedarf - stock

        if to_order > 0:
            results.append({
                'Lieferant': lieferant,
                'Hersteller': hersteller,
                'Name': art_name,
                'Bestellmenge': to_order
            })

    if not results:
        return True, "Keine Bestellungen notwendig.", {'mode': mode, 'segments': []}

    df_out = pd.DataFrame(results).sort_values(by=['Lieferant', 'Hersteller', 'Name'])
    segments = []
    for (lieferant, hersteller), group in df_out.groupby(['Lieferant', 'Hersteller'], sort=False):
        items = []
        for _, row in group.iterrows():
            items.append({
                'hersteller': str(row['Hersteller']),
                'name': str(row['Name']),
                'amount': int(row['Bestellmenge'])
            })
        segments.append({
            'lieferant': lieferant,
            'hersteller': hersteller,
            'items': items
        })

    return True, "OK", {'mode': mode, 'segments': segments}


def create_order_pdf(data, filename=None):
    if not filename:
        filename = os.path.join(BASE_DIR, f"Bestellung_{sanitize_filename(data.get('mode', 'Bestellung'))}.pdf")

    try:
        c = canvas.Canvas(filename, pagesize=A4)
        width, height = A4
        margin = 40
        y = height - margin - 50

        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin, height - margin, f"Bestellvorschlag: {data.get('mode', '')}")

        idx = 0
        for segment in data.get('segments', []):
            if y < 80:
                c.showPage()
                y = height - margin - 20

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, f"Lieferant: {segment['lieferant']}")
            c.drawString(margin + 360, y, f"Hersteller: {segment['hersteller']}")
            y -= 22
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin, y, "Hersteller")
            c.drawString(margin + 100, y, "Artikelname")
            c.drawString(margin + 360, y, "Menge")
            c.drawString(margin + 420, y, "Bestellt")
            c.line(margin, y-5, width-margin, y-5)
            y -= 20

            for item in segment.get('items', []):
                if y < 70:
                    c.showPage()
                    y = height - margin - 20
                c.setFont("Helvetica", 9)
                c.drawString(margin, y, item.get('hersteller', '')[:18])
                c.drawString(margin + 100, y, item.get('name', '')[:50])
                c.drawString(margin + 360, y, str(item.get('amount', '')))
                c.acroForm.checkbox(name=f"b_{idx}", x=margin + 425, y=y-2, size=12)
                c.setStrokeColor(colors.lightgrey)
                c.line(margin, y-5, width-margin, y-5)
                c.setStrokeColor(colors.black)
                y -= 18
                idx += 1

            y -= 10

        c.save()
        return True, f"Erfolg! PDF erstellt:\n{filename}"
    except Exception as e:
        return False, f"Fehler: {e}"


def run_orders(mode, min_stock, apply_buffer, sales_file, art_file, shops):
    success, message, data = build_order_data(mode, min_stock, apply_buffer, sales_file, art_file, shops)
    if not success:
        return False, message
    if not data['segments']:
        return True, "Keine Bestellungen notwendig."
    return create_order_pdf(data)

# ==========================================
# LOGIK: LAGERBEWEGUNG
# ==========================================
def build_transfer_data(source_shop, min_stock, apply_buffer, sales_file, art_file, shops):
    target_shops = [s for s in shops if s != source_shop]
    success, _, art_df, sales_pivot = load_and_prep_data(sales_file, art_file)
    if not success:
        return False, sales_pivot, None

    results = []
    for _, row in art_df.iterrows():
        art_no = str(row.get('Artikel-Nr', '')).strip()
        if not art_no or art_no == 'nan':
            continue

        stock_source = int(float(row.get(f'Bestand: {source_shop}', 0))) if pd.notnull(row.get(f'Bestand: {source_shop}')) else 0
        sales_source = int(sales_pivot.at[art_no, source_shop]) if not sales_pivot.empty and art_no in sales_pivot.index and source_shop in sales_pivot.columns else 0
        bedarf_source = calculate_need(sales_source, min_stock, apply_buffer)
        surplus = stock_source - bedarf_source

        if surplus <= 0:
            continue

        target_sales = {
            ts: (int(sales_pivot.at[art_no, ts]) if not sales_pivot.empty and art_no in sales_pivot.index and ts in sales_pivot.columns else 0)
            for ts in target_shops
        }
        dist = distribute_surplus(surplus, target_sales)
        if sum(dist.values()) <= 0:
            continue

        hersteller = str(row.get('Hersteller', '')).strip()
        hersteller = hersteller if hersteller and hersteller != 'nan' else 'Ohne Hersteller'

        results.append({
            'hersteller': hersteller,
            'name': str(row.get('Bezeichnung', '')),
            'amounts': {ts: dist[ts] for ts in target_shops}
        })

    if not results:
        return True, 'Keine Umbuchungen nötig.', {
            'source_shop': source_shop,
            'target_shops': target_shops,
            'segments': []
        }

    results.sort(key=lambda r: (r['hersteller'].lower(), r['name'].lower()))
    segments = []
    current_hersteller = None
    for item in results:
        if item['hersteller'] != current_hersteller:
            current_hersteller = item['hersteller']
            segments.append({'hersteller': current_hersteller, 'items': []})
        segments[-1]['items'].append(item)

    return True, 'OK', {
        'source_shop': source_shop,
        'target_shops': target_shops,
        'segments': segments
    }


def create_transfer_pdf(data, filename=None):
    if not filename:
        filename = os.path.join(BASE_DIR, f"Lagerbewegung_{sanitize_filename(data.get('source_shop', ''))}.pdf")

    try:
        c = canvas.Canvas(filename, pagesize=A4)
        width, height = A4
        margin = 40
        y = height - 80

        c.setFont('Helvetica-Bold', 14)
        c.drawString(margin, height - 40, f"Lagerbewegung: Von {data.get('source_shop', '')}")

        idx = 0
        for segment in data.get('segments', []):
            if y < 70:
                c.showPage()
                y = height - 50

            c.setFont('Helvetica-Bold', 11)
            c.drawString(margin, y, f"Hersteller: {segment['hersteller']}")
            y -= 20
            c.setFont('Helvetica-Bold', 10)
            c.drawString(margin, y, 'Artikelname')
            x_offset = margin + 250
            for ts in data.get('target_shops', []):
                c.drawString(x_offset, y, ts[:10])
                x_offset += 60
            c.drawString(x_offset, y, 'Erledigt')
            c.line(margin, y-5, width-margin, y-5)
            y -= 20

            for item in segment.get('items', []):
                if y < 70:
                    c.showPage()
                    y = height - 50
                c.setFont('Helvetica', 9)
                c.drawString(margin, y, item['name'][:45])
                x_offset = margin + 250
                for ts in data.get('target_shops', []):
                    amount = item['amounts'].get(ts, 0)
                    if amount > 0:
                        c.drawString(x_offset + 10, y, str(amount))
                    x_offset += 60
                c.acroForm.checkbox(name=f'done_{idx}', x=x_offset + 10, y=y-2, size=12)
                c.setStrokeColor(colors.lightgrey)
                c.line(margin, y-5, width-margin, y-5)
                c.setStrokeColor(colors.black)
                y -= 18
                idx += 1

            y -= 10

        c.save()
        return True, f"PDF erstellt:\n{filename}"
    except Exception as e:
        return False, f"Fehler: {e}"


def run_transfers(source_shop, min_stock, apply_buffer, sales_file, art_file, shops):
    success, message, data = build_transfer_data(source_shop, min_stock, apply_buffer, sales_file, art_file, shops)
    if not success:
        return False, message
    if not data['segments']:
        return True, 'Keine Umbuchungen nötig.'
    return create_transfer_pdf(data)

# ==========================================
# UI
# ==========================================

class SegmentEditor(tk.Toplevel):
    def __init__(self, master, preview_window, segment_index):
        super().__init__(master)
        self.preview_window = preview_window
        self.segment_index = segment_index
        self.data = preview_window.data
        self.is_new = segment_index >= len(self.data['segments'])
        self.title('Segment bearbeiten' if not self.is_new else 'Neues Segment hinzufügen')
        self.geometry('420x240')
        self.resizable(False, False)
        self.build_ui()
        self.load_segment()

    def build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text='Lieferant:').grid(row=0, column=0, sticky='w')
        self.ent_supplier = ttk.Entry(frame, width=45)
        self.ent_supplier.grid(row=1, column=0, columnspan=2, pady=5)

        ttk.Label(frame, text='Hersteller:').grid(row=2, column=0, sticky='w')
        self.ent_manufacturer = ttk.Entry(frame, width=45)
        self.ent_manufacturer.grid(row=3, column=0, columnspan=2, pady=5)

        nav = ttk.Frame(frame)
        nav.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky='ew')
        ttk.Button(nav, text='←', width=4, command=lambda: self.navigate(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text='→', width=4, command=lambda: self.navigate(1)).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav, text='Zu Artikeln wechseln', command=self.open_articles).pack(side=tk.LEFT, padx=10)

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, pady=15, sticky='ew')
        ttk.Button(actions, text='Speichern', command=self.save).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(actions, text='Abbrechen', command=self.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    def load_segment(self):
        if self.is_new:
            self.ent_supplier.delete(0, tk.END)
            self.ent_manufacturer.delete(0, tk.END)
        else:
            segment = self.data['segments'][self.segment_index]
            self.ent_supplier.delete(0, tk.END)
            self.ent_supplier.insert(0, segment.get('lieferant', ''))
            self.ent_manufacturer.delete(0, tk.END)
            self.ent_manufacturer.insert(0, segment.get('hersteller', ''))

    def navigate(self, direction):
        new_index = self.segment_index + direction
        if 0 <= new_index <= len(self.data['segments']):
            self.segment_index = new_index
            self.is_new = new_index >= len(self.data['segments'])
            self.title('Segment bearbeiten' if not self.is_new else 'Neues Segment hinzufügen')
            self.load_segment()

    def open_articles(self):
        if self.data['segments']:
            target_index = min(self.segment_index, len(self.data['segments']) - 1)
            self.preview_window.open_article_editor(target_index, 0)
            self.destroy()

    def save(self):
        supplier = self.ent_supplier.get().strip() or 'Unbekannter Lieferant'
        manufacturer = self.ent_manufacturer.get().strip() or '-'

        if self.is_new:
            self.data['segments'].append({
                'lieferant': supplier,
                'hersteller': manufacturer,
                'items': []
            })
        else:
            segment = self.data['segments'][self.segment_index]
            segment['lieferant'] = supplier
            segment['hersteller'] = manufacturer
            for item in segment['items']:
                if not item.get('hersteller'):
                    item['hersteller'] = manufacturer

        self.preview_window.refresh()
        self.destroy()


class ArticleEditor(tk.Toplevel):
    def __init__(self, master, preview_window, segment_index, article_index=None):
        super().__init__(master)
        self.preview_window = preview_window
        self.segment_index = segment_index
        self.article_index = article_index
        self.data = preview_window.data
        self.is_new = article_index is None or article_index >= len(self.data['segments'][segment_index]['items'])
        self.title('Artikel bearbeiten' if not self.is_new else 'Neuen Artikel hinzufügen')
        self.geometry('460x300')
        self.resizable(False, False)
        self.build_ui()
        self.load_article()

    def build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text='Hersteller:').grid(row=0, column=0, sticky='w')
        self.ent_hersteller = ttk.Entry(frame, width=50)
        self.ent_hersteller.grid(row=1, column=0, columnspan=2, pady=5)

        ttk.Label(frame, text='Artikelname:').grid(row=2, column=0, sticky='w')
        self.ent_name = ttk.Entry(frame, width=50)
        self.ent_name.grid(row=3, column=0, columnspan=2, pady=5)

        ttk.Label(frame, text='Menge:').grid(row=4, column=0, sticky='w')
        self.ent_amount = ttk.Entry(frame, width=20)
        self.ent_amount.grid(row=5, column=0, pady=5, sticky='w')

        nav = ttk.Frame(frame)
        nav.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky='ew')
        ttk.Button(nav, text='←', width=4, command=lambda: self.navigate(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text='→', width=4, command=lambda: self.navigate(1)).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav, text='Zu Lieferant/Hersteller wechseln', command=self.open_segment).pack(side=tk.LEFT, padx=10)

        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, columnspan=2, pady=15, sticky='ew')
        ttk.Button(actions, text='Speichern', command=self.save).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(actions, text='Abbrechen', command=self.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        extra = ttk.Frame(frame)
        extra.grid(row=8, column=0, columnspan=2, pady=(5, 0), sticky='ew')
        ttk.Button(extra, text='Artikel entfernen', command=self.remove).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(extra, text='Artikel hinzufügen', command=self.add_new).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    def load_article(self):
        segment = self.data['segments'][self.segment_index]
        if self.is_new:
            self.ent_hersteller.delete(0, tk.END)
            self.ent_hersteller.insert(0, segment.get('hersteller', ''))
            self.ent_name.delete(0, tk.END)
            self.ent_amount.delete(0, tk.END)
        else:
            article = segment['items'][self.article_index]
            self.ent_hersteller.delete(0, tk.END)
            self.ent_hersteller.insert(0, article.get('hersteller', segment.get('hersteller', '')))
            self.ent_name.delete(0, tk.END)
            self.ent_name.insert(0, article.get('name', ''))
            self.ent_amount.delete(0, tk.END)
            self.ent_amount.insert(0, str(article.get('amount', '')))

    def navigate(self, direction):
        segment = self.data['segments'][self.segment_index]
        if self.article_index is None:
            self.article_index = len(segment['items']) - 1 if segment['items'] else None
        else:
            self.article_index += direction
        if self.article_index is None:
            return
        if self.article_index < 0:
            self.article_index = 0
        if self.article_index >= len(segment['items']):
            self.article_index = len(segment['items']) - 1
        self.is_new = self.article_index is None or self.article_index >= len(segment['items'])
        self.title('Artikel bearbeiten' if not self.is_new else 'Neuen Artikel hinzufügen')
        self.load_article()

    def open_segment(self):
        self.preview_window.open_segment_editor(self.segment_index)
        self.destroy()

    def save(self):
        hersteller = self.ent_hersteller.get().strip() or self.data['segments'][self.segment_index].get('hersteller', '-')
        name = self.ent_name.get().strip() or 'Unbenannter Artikel'
        try:
            amount = max(0, int(self.ent_amount.get().strip() or 0))
        except ValueError:
            amount = 0

        article_data = {'hersteller': hersteller, 'name': name, 'amount': amount}
        segment = self.data['segments'][self.segment_index]

        if self.is_new or self.article_index is None or self.article_index >= len(segment['items']):
            segment['items'].append(article_data)
        else:
            segment['items'][self.article_index] = article_data

        segment['items'].sort(key=lambda i: (i.get('hersteller', '').lower(), i.get('name', '').lower()))
        self.preview_window.refresh()
        self.destroy()

    def remove(self):
        segment = self.data['segments'][self.segment_index]
        if self.is_new or self.article_index is None or self.article_index >= len(segment['items']):
            return
        del segment['items'][self.article_index]
        self.preview_window.refresh()
        self.destroy()

    def add_new(self):
        segment = self.data['segments'][self.segment_index]
        new_item = {'hersteller': segment.get('hersteller', '-'), 'name': '', 'amount': 0}
        segment['items'].append(new_item)
        self.article_index = len(segment['items']) - 1
        self.is_new = False
        self.load_article()


class PreviewWindow(tk.Toplevel):
    def __init__(self, master, data, sales_file, art_file, shops):
        super().__init__(master)
        self.master = master
        self.data = data
        self.sales_file = sales_file
        self.art_file = art_file
        self.shops = shops
        self.zoom = 1.0
        self.title('Bestellvorschau')
        self.geometry('980x700')
        self.build_ui()
        self.refresh()

    def build_ui(self):
        toolbar = ttk.Frame(self, padding=10)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text='+', width=4, command=self.zoom_in).pack(side=tk.LEFT)
        ttk.Button(toolbar, text='-', width=4, command=self.zoom_out).pack(side=tk.LEFT, padx=5)
        self.zoom_label = ttk.Label(toolbar, text='Zoom: 100%')
        self.zoom_label.pack(side=tk.LEFT, padx=10)
        ttk.Button(toolbar, text='PDF Generieren', command=self.generate_pdf).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(body, bg='#f4f6f9')
        self.v_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind_all('<Control-MouseWheel>', self.on_zoom_wheel)
        self.canvas.bind_all('<Control-Button-4>', lambda e: self.zoom_in())
        self.canvas.bind_all('<Control-Button-5>', lambda e: self.zoom_out())

    def refresh(self):
        self.canvas.delete('all')
        self.draw_preview()
        self.zoom_label.config(text=f'Zoom: {int(self.zoom * 100)}%')

    def draw_preview(self):
        content_width = max(880, int(880 * self.zoom))
        x = 20
        y = 20
        segment_font = ('Helvetica', max(10, int(10 * self.zoom)), 'bold')
        row_font = ('Helvetica', max(8, int(9 * self.zoom)))
        header_font = ('Helvetica', max(8, int(9 * self.zoom)), 'bold')

        for seg_index, segment in enumerate(self.data.get('segments', [])):
            segment_frame = tk.Frame(self.canvas, bd=1, relief='solid', bg='#ffffff')
            title_text = f"Lieferant: {segment['lieferant']}  |  Hersteller: {segment['hersteller']}"
            tk.Label(segment_frame, text=title_text, font=segment_font, bg='#dfefff', anchor='w').pack(fill=tk.X, padx=8, pady=8)

            header = tk.Frame(segment_frame, bg='#f0f4ff')
            header.pack(fill=tk.X, padx=8, pady=(0, 4))
            tk.Label(header, text='Hersteller', width=18, anchor='w', bg='#f0f4ff', font=header_font).pack(side=tk.LEFT)
            tk.Label(header, text='Artikelname', width=42, anchor='w', bg='#f0f4ff', font=header_font).pack(side=tk.LEFT)
            tk.Label(header, text='Menge', width=10, anchor='w', bg='#f0f4ff', font=header_font).pack(side=tk.LEFT)

            for art_index, item in enumerate(segment['items']):
                row = tk.Frame(segment_frame, bg='#ffffff', pady=2)
                row.pack(fill=tk.X, padx=8, pady=1)
                self.apply_hover(row, '#ffffff', '#e6f2ff')
                row.bind('<Button-1>', lambda e, si=seg_index, ai=art_index: self.open_article_editor(si, ai))

                lbl_h = tk.Label(row, text=item.get('hersteller', ''), width=18, anchor='w', bg='#ffffff', font=row_font)
                lbl_h.pack(side=tk.LEFT)
                lbl_n = tk.Label(row, text=item.get('name', ''), width=42, anchor='w', bg='#ffffff', font=row_font)
                lbl_n.pack(side=tk.LEFT)
                lbl_a = tk.Label(row, text=str(item.get('amount', '')), width=10, anchor='w', bg='#ffffff', font=row_font)
                lbl_a.pack(side=tk.LEFT)

                for widget in (lbl_h, lbl_n, lbl_a):
                    widget.bind('<Button-1>', lambda e, si=seg_index, ai=art_index: self.open_article_editor(si, ai))

            add_frame = tk.Frame(segment_frame, bg='#eef7ff')
            add_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
            add_label = tk.Label(add_frame, text='+ Artikel hinzufügen', fg='#0d47a1', bg='#eef7ff', font=row_font, anchor='w')
            add_label.pack(fill=tk.X, padx=6, pady=6)
            add_frame.bind('<Button-1>', lambda e, si=seg_index: self.open_article_editor(si, None))
            add_label.bind('<Button-1>', lambda e, si=seg_index: self.open_article_editor(si, None))

            segment_frame.bind('<Enter>', lambda e, w=segment_frame: w.config(bg='#d9f0ff'))
            segment_frame.bind('<Leave>', lambda e, w=segment_frame: w.config(bg='#ffffff'))
            segment_frame.bind('<Button-1>', lambda e, si=seg_index: self.open_segment_editor(si))

            self.canvas.create_window(x, y, anchor='nw', window=segment_frame, width=content_width)
            y += segment_frame.winfo_reqheight() + 16

        add_segment = tk.Frame(self.canvas, bd=2, relief='dashed', bg='#eef7ff')
        add_label = tk.Label(add_segment, text='+ Neues Segment hinzufügen', fg='#0d47a1', bg='#eef7ff', font=segment_font)
        add_label.pack(fill=tk.BOTH, padx=8, pady=16)
        add_segment.bind('<Button-1>', lambda e: self.open_segment_editor(len(self.data['segments'])))
        add_label.bind('<Button-1>', lambda e: self.open_segment_editor(len(self.data['segments'])))
        self.canvas.create_window(x, y, anchor='nw', window=add_segment, width=content_width)
        y += add_segment.winfo_reqheight() + 20

        self.canvas.configure(scrollregion=(0, 0, content_width + 40, y + 20))

    def apply_hover(self, widget, base, hover_color):
        widget.bind('<Enter>', lambda e: widget.config(bg=hover_color))
        widget.bind('<Leave>', lambda e: widget.config(bg=base))

    def open_segment_editor(self, segment_index):
        SegmentEditor(self, self, segment_index)

    def open_article_editor(self, segment_index, article_index=None):
        if segment_index >= len(self.data['segments']):
            return
        ArticleEditor(self, self, segment_index, article_index)

    def zoom_in(self):
        if self.zoom < 2.0:
            self.zoom = round(self.zoom + 0.1, 2)
            self.refresh()

    def zoom_out(self):
        if self.zoom > 0.5:
            self.zoom = round(self.zoom - 0.1, 2)
            self.refresh()

    def on_zoom_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def generate_pdf(self):
        success, message = create_order_pdf(self.data)
        if success:
            messagebox.showinfo('Erfolg', message)
        else:
            messagebox.showerror('Fehler', message)


class TransferSegmentEditor(tk.Toplevel):
    def __init__(self, master, preview_window, segment_index):
        super().__init__(master)
        self.preview_window = preview_window
        self.segment_index = segment_index
        self.data = preview_window.data
        self.is_new = segment_index >= len(self.data['segments'])
        self.title('Hersteller bearbeiten' if not self.is_new else 'Neues Hersteller-Segment hinzufügen')
        self.geometry('380x180')
        self.resizable(False, False)
        self.build_ui()
        self.load_segment()

    def build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text='Hersteller:').grid(row=0, column=0, sticky='w')
        self.ent_hersteller = ttk.Entry(frame, width=45)
        self.ent_hersteller.grid(row=1, column=0, pady=5)

        nav = ttk.Frame(frame)
        nav.grid(row=2, column=0, pady=(10, 0), sticky='ew')
        ttk.Button(nav, text='←', width=4, command=lambda: self.navigate(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text='→', width=4, command=lambda: self.navigate(1)).pack(side=tk.LEFT, padx=5)

        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, pady=15, sticky='ew')
        ttk.Button(actions, text='Speichern', command=self.save).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(actions, text='Abbrechen', command=self.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    def load_segment(self):
        if self.is_new:
            self.ent_hersteller.delete(0, tk.END)
        else:
            segment = self.data['segments'][self.segment_index]
            self.ent_hersteller.delete(0, tk.END)
            self.ent_hersteller.insert(0, segment.get('hersteller', ''))

    def navigate(self, direction):
        new_index = self.segment_index + direction
        if 0 <= new_index <= len(self.data['segments']):
            self.segment_index = new_index
            self.is_new = new_index >= len(self.data['segments'])
            self.title('Hersteller bearbeiten' if not self.is_new else 'Neues Hersteller-Segment hinzufügen')
            self.load_segment()

    def save(self):
        hersteller = self.ent_hersteller.get().strip() or 'Ohne Hersteller'

        if self.is_new:
            self.data['segments'].append({
                'hersteller': hersteller,
                'items': []
            })
        else:
            segment = self.data['segments'][self.segment_index]
            segment['hersteller'] = hersteller
            for item in segment['items']:
                if not item.get('hersteller'):
                    item['hersteller'] = hersteller

        self.preview_window.refresh()
        self.destroy()


class TransferArticleEditor(tk.Toplevel):
    def __init__(self, master, preview_window, segment_index, article_index=None):
        super().__init__(master)
        self.preview_window = preview_window
        self.segment_index = segment_index
        self.article_index = article_index
        self.data = preview_window.data
        self.shop_entries = {}
        self.is_new = article_index is None or article_index >= len(self.data['segments'][segment_index]['items'])
        self.title('Artikel bearbeiten' if not self.is_new else 'Neuen Artikel hinzufügen')
        self.geometry('520x380')
        self.resizable(False, False)
        self.build_ui()
        self.load_article()

    def build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text='Hersteller:').grid(row=0, column=0, sticky='w')
        self.ent_hersteller = ttk.Entry(frame, width=55)
        self.ent_hersteller.grid(row=1, column=0, columnspan=2, pady=5)

        ttk.Label(frame, text='Artikelname:').grid(row=2, column=0, sticky='w')
        self.ent_name = ttk.Entry(frame, width=55)
        self.ent_name.grid(row=3, column=0, columnspan=2, pady=5)

        ttk.Label(frame, text='Mengen je Zielshop:').grid(row=4, column=0, sticky='w', pady=(10, 0))
        qty_frame = ttk.Frame(frame)
        qty_frame.grid(row=5, column=0, columnspan=2, sticky='w')

        for idx, shop in enumerate(self.data.get('target_shops', [])):
            ttk.Label(qty_frame, text=f'{shop}:').grid(row=idx, column=0, sticky='w', pady=2)
            ent = ttk.Entry(qty_frame, width=15)
            ent.grid(row=idx, column=1, pady=2, padx=(5, 0), sticky='w')
            self.shop_entries[shop] = ent

        nav = ttk.Frame(frame)
        nav.grid(row=6 + len(self.shop_entries), column=0, columnspan=2, pady=(10, 0), sticky='ew')
        ttk.Button(nav, text='←', width=4, command=lambda: self.navigate(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text='→', width=4, command=lambda: self.navigate(1)).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav, text='Zu Hersteller wechseln', command=self.open_segment).pack(side=tk.LEFT, padx=10)

        actions = ttk.Frame(frame)
        actions.grid(row=7 + len(self.shop_entries), column=0, columnspan=2, pady=15, sticky='ew')
        ttk.Button(actions, text='Speichern', command=self.save).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(actions, text='Abbrechen', command=self.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        extra = ttk.Frame(frame)
        extra.grid(row=8 + len(self.shop_entries), column=0, columnspan=2, pady=(5, 0), sticky='ew')
        ttk.Button(extra, text='Artikel entfernen', command=self.remove).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(extra, text='Artikel hinzufügen', command=self.add_new).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    def load_article(self):
        segment = self.data['segments'][self.segment_index]
        if self.is_new:
            self.ent_hersteller.delete(0, tk.END)
            self.ent_hersteller.insert(0, segment.get('hersteller', ''))
            self.ent_name.delete(0, tk.END)
            for ent in self.shop_entries.values():
                ent.delete(0, tk.END)
        else:
            article = segment['items'][self.article_index]
            self.ent_hersteller.delete(0, tk.END)
            self.ent_hersteller.insert(0, article.get('hersteller', segment.get('hersteller', '')))
            self.ent_name.delete(0, tk.END)
            self.ent_name.insert(0, article.get('name', ''))
            for shop, ent in self.shop_entries.items():
                ent.delete(0, tk.END)
                ent.insert(0, str(article.get('amounts', {}).get(shop, 0)))

    def navigate(self, direction):
        segment = self.data['segments'][self.segment_index]
        if self.article_index is None:
            self.article_index = len(segment['items']) - 1 if segment['items'] else None
        else:
            self.article_index += direction
        if self.article_index is None:
            return
        if self.article_index < 0:
            self.article_index = 0
        if self.article_index >= len(segment['items']):
            self.article_index = len(segment['items']) - 1
        self.is_new = self.article_index is None or self.article_index >= len(segment['items'])
        self.title('Artikel bearbeiten' if not self.is_new else 'Neuen Artikel hinzufügen')
        self.load_article()

    def open_segment(self):
        self.preview_window.open_segment_editor(self.segment_index)
        self.destroy()

    def save(self):
        hersteller = self.ent_hersteller.get().strip() or self.data['segments'][self.segment_index].get('hersteller', '-')
        name = self.ent_name.get().strip() or 'Unbenannter Artikel'
        amounts = {}
        for shop, ent in self.shop_entries.items():
            try:
                amounts[shop] = max(0, int(ent.get().strip() or 0))
            except ValueError:
                amounts[shop] = 0

        article_data = {'hersteller': hersteller, 'name': name, 'amounts': amounts}
        segment = self.data['segments'][self.segment_index]

        if self.is_new or self.article_index is None or self.article_index >= len(segment['items']):
            segment['items'].append(article_data)
        else:
            segment['items'][self.article_index] = article_data

        segment['items'].sort(key=lambda i: (i.get('hersteller', '').lower(), i.get('name', '').lower()))
        self.preview_window.refresh()
        self.destroy()

    def remove(self):
        segment = self.data['segments'][self.segment_index]
        if self.is_new or self.article_index is None or self.article_index >= len(segment['items']):
            return
        del segment['items'][self.article_index]
        self.preview_window.refresh()
        self.destroy()

    def add_new(self):
        segment = self.data['segments'][self.segment_index]
        new_item = {'hersteller': segment.get('hersteller', '-'), 'name': '', 'amounts': {shop: 0 for shop in self.data.get('target_shops', [])}}
        segment['items'].append(new_item)
        self.article_index = len(segment['items']) - 1
        self.is_new = False
        self.load_article()


class TransferPreviewWindow(tk.Toplevel):
    def __init__(self, master, data, sales_file, art_file, shops):
        super().__init__(master)
        self.master = master
        self.data = data
        self.sales_file = sales_file
        self.art_file = art_file
        self.shops = shops
        self.zoom = 1.0
        self.title('Lagerbewegung Vorschau')
        self.geometry('980x700')
        self.build_ui()
        self.refresh()

    def build_ui(self):
        toolbar = ttk.Frame(self, padding=10)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text='+', width=4, command=self.zoom_in).pack(side=tk.LEFT)
        ttk.Button(toolbar, text='-', width=4, command=self.zoom_out).pack(side=tk.LEFT, padx=5)
        self.zoom_label = ttk.Label(toolbar, text='Zoom: 100%')
        self.zoom_label.pack(side=tk.LEFT, padx=10)
        ttk.Button(toolbar, text='PDF Generieren', command=self.generate_pdf).pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(body, bg='#f4f6f9')
        self.v_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind_all('<Control-MouseWheel>', self.on_zoom_wheel)
        self.canvas.bind_all('<Control-Button-4>', lambda e: self.zoom_in())
        self.canvas.bind_all('<Control-Button-5>', lambda e: self.zoom_out())

    def refresh(self):
        self.canvas.delete('all')
        self.draw_preview()
        self.zoom_label.config(text=f'Zoom: {int(self.zoom * 100)}%')

    def draw_preview(self):
        content_width = max(880, int(880 * self.zoom))
        x = 20
        y = 20
        segment_font = ('Helvetica', max(10, int(10 * self.zoom)), 'bold')
        row_font = ('Helvetica', max(8, int(9 * self.zoom)))
        header_font = ('Helvetica', max(8, int(9 * self.zoom)), 'bold')

        for seg_index, segment in enumerate(self.data.get('segments', [])):
            segment_frame = tk.Frame(self.canvas, bd=1, relief='solid', bg='#ffffff')
            title_text = f"Hersteller: {segment['hersteller']}"
            tk.Label(segment_frame, text=title_text, font=segment_font, bg='#dfefff', anchor='w').pack(fill=tk.X, padx=8, pady=8)

            header = tk.Frame(segment_frame, bg='#f0f4ff')
            header.pack(fill=tk.X, padx=8, pady=(0, 4))
            tk.Label(header, text='Artikelname', width=42, anchor='w', bg='#f0f4ff', font=header_font).pack(side=tk.LEFT)
            for shop in self.data.get('target_shops', []):
                tk.Label(header, text=shop[:10], width=10, anchor='w', bg='#f0f4ff', font=header_font).pack(side=tk.LEFT)

            for art_index, item in enumerate(segment['items']):
                row = tk.Frame(segment_frame, bg='#ffffff', pady=2)
                row.pack(fill=tk.X, padx=8, pady=1)
                self.apply_hover(row, '#ffffff', '#e6f2ff')
                row.bind('<Button-1>', lambda e, si=seg_index, ai=art_index: self.open_article_editor(si, ai))

                lbl_n = tk.Label(row, text=item.get('name', ''), width=42, anchor='w', bg='#ffffff', font=row_font)
                lbl_n.pack(side=tk.LEFT)
                for shop in self.data.get('target_shops', []):
                    lbl_amt = tk.Label(row, text=str(item.get('amounts', {}).get(shop, 0)), width=10, anchor='w', bg='#ffffff', font=row_font)
                    lbl_amt.pack(side=tk.LEFT)
                    lbl_amt.bind('<Button-1>', lambda e, si=seg_index, ai=art_index: self.open_article_editor(si, ai))
                for widget in (lbl_n,):
                    widget.bind('<Button-1>', lambda e, si=seg_index, ai=art_index: self.open_article_editor(si, ai))

            add_frame = tk.Frame(segment_frame, bg='#eef7ff')
            add_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
            add_label = tk.Label(add_frame, text='+ Artikel hinzufügen', fg='#0d47a1', bg='#eef7ff', font=row_font, anchor='w')
            add_label.pack(fill=tk.X, padx=6, pady=6)
            add_frame.bind('<Button-1>', lambda e, si=seg_index: self.open_article_editor(si, None))
            add_label.bind('<Button-1>', lambda e, si=seg_index: self.open_article_editor(si, None))

            segment_frame.bind('<Enter>', lambda e, w=segment_frame: w.config(bg='#d9f0ff'))
            segment_frame.bind('<Leave>', lambda e, w=segment_frame: w.config(bg='#ffffff'))
            segment_frame.bind('<Button-1>', lambda e, si=seg_index: self.open_segment_editor(si))

            self.canvas.create_window(x, y, anchor='nw', window=segment_frame, width=content_width)
            y += segment_frame.winfo_reqheight() + 16

        add_segment = tk.Frame(self.canvas, bd=2, relief='dashed', bg='#eef7ff')
        add_label = tk.Label(add_segment, text='+ Neues Hersteller-Segment hinzufügen', fg='#0d47a1', bg='#eef7ff', font=segment_font)
        add_label.pack(fill=tk.BOTH, padx=8, pady=16)
        add_segment.bind('<Button-1>', lambda e: self.open_segment_editor(len(self.data['segments'])))
        add_label.bind('<Button-1>', lambda e: self.open_segment_editor(len(self.data['segments'])))
        self.canvas.create_window(x, y, anchor='nw', window=add_segment, width=content_width)
        y += add_segment.winfo_reqheight() + 20

        self.canvas.configure(scrollregion=(0, 0, content_width + 40, y + 20))

    def apply_hover(self, widget, base, hover_color):
        widget.bind('<Enter>', lambda e: widget.config(bg=hover_color))
        widget.bind('<Leave>', lambda e: widget.config(bg=base))

    def open_segment_editor(self, segment_index):
        TransferSegmentEditor(self, self, segment_index)

    def open_article_editor(self, segment_index, article_index=None):
        if segment_index >= len(self.data['segments']):
            return
        TransferArticleEditor(self, self, segment_index, article_index)

    def zoom_in(self):
        if self.zoom < 2.0:
            self.zoom = round(self.zoom + 0.1, 2)
            self.refresh()

    def zoom_out(self):
        if self.zoom > 0.5:
            self.zoom = round(self.zoom - 0.1, 2)
            self.refresh()

    def on_zoom_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def generate_pdf(self):
        success, message = create_transfer_pdf(self.data)
        if success:
            messagebox.showinfo('Erfolg', message)
        else:
            messagebox.showerror('Fehler', message)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Bestands- & Bestelloptimierung v2.0')
        self.geometry('580x650')
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        self.sales_file = get_latest_file('*articlessold*.csv')
        self.art_file = get_latest_file('*articles_*stammdaten*.csv') or get_latest_file('*articles_*.csv')
        self.shops = get_dynamic_shops(self.sales_file)
        self.build_ui()

    def build_ui(self):
        header = ttk.Frame(self, padding=20)
        header.pack(fill=tk.X)
        ttk.Label(header, text='Datenquellen:', font=('Sans', 12, 'bold')).pack(anchor='w')
        ttk.Label(header, text=f"Verkäufe: {os.path.basename(self.sales_file) if self.sales_file else 'FEHLT'}", foreground='green' if self.sales_file else 'red').pack(anchor='w')
        ttk.Label(header, text=f"Stammdaten: {os.path.basename(self.art_file) if self.art_file else 'FEHLT'}", foreground='green' if self.art_file else 'red').pack(anchor='w')

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        self.tab_o = ttk.Frame(self.nb, padding=20)
        self.tab_t = ttk.Frame(self.nb, padding=20)
        self.nb.add(self.tab_o, text=' Bestellvorschlag ')
        self.nb.add(self.tab_t, text=' Lagerbewegung ')

        shop_list = self.shops if self.shops else ['Keine Daten']
        first_shop = shop_list[0] if shop_list else ''

        ttk.Label(self.tab_o, text='Für welches Lager soll bestellt werden?', font=('Sans', 11, 'bold')).pack(anchor='w')
        self.o_shop = tk.StringVar(value='Zentrale Bestellung')
        ttk.Combobox(self.tab_o, textvariable=self.o_shop, values=['Zentrale Bestellung'] + shop_list, state='readonly').pack(fill=tk.X, pady=5)

        ttk.Label(self.tab_o, text='Mindestbestand:', font=('Sans', 11, 'bold')).pack(anchor='w', pady=(10, 0))
        self.o_min = tk.IntVar(value=0)
        l_min = ttk.Label(self.tab_o, text='0 Stück')
        ttk.Scale(self.tab_o, from_=0, to=20, variable=self.o_min, command=lambda v: l_min.config(text=f"{int(float(v))} Stück")).pack(fill=tk.X)
        l_min.pack()

        self.o_buf = tk.BooleanVar()
        ttk.Checkbutton(self.tab_o, text='Zukunftspuffer: +20% Reserve auf historische Verkäufe', variable=self.o_buf).pack(anchor='w', pady=15)
        ttk.Button(self.tab_o, text='Bestellvorschau öffnen', command=self.do_o).pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(self.tab_t, text='Von wo wird umgebucht?', font=('Sans', 11, 'bold')).pack(anchor='w')
        self.t_shop = tk.StringVar(value=first_shop)
        ttk.Combobox(self.tab_t, textvariable=self.t_shop, values=shop_list, state='readonly').pack(fill=tk.X, pady=5)

        ttk.Label(self.tab_t, text='Mindestbestand (Bleibt im Shop):', font=('Sans', 11, 'bold')).pack(anchor='w', pady=(10, 0))
        self.t_min = tk.IntVar(value=0)
        l_tmin = ttk.Label(self.tab_t, text='0 Stück')
        ttk.Scale(self.tab_t, from_=0, to=20, variable=self.t_min, command=lambda v: l_tmin.config(text=f"{int(float(v))} Stück")).pack(fill=tk.X)
        l_tmin.pack()

        self.t_buf = tk.BooleanVar()
        ttk.Checkbutton(self.tab_t, text='Zukunftspuffer: +20% Verkaufsreserve behalten', variable=self.t_buf).pack(anchor='w', pady=15)
        ttk.Button(self.tab_t, text='Lagerbewegung berechnen', command=self.do_t).pack(fill=tk.X, side=tk.BOTTOM)

    def do_o(self):
        if not self.shops:
            return messagebox.showerror('Fehler', 'Keine Shops gefunden!')
        success, message, data = build_order_data(
            self.o_shop.get(), self.o_min.get(), self.o_buf.get(), self.sales_file, self.art_file, self.shops
        )
        if not success:
            return messagebox.showerror('Fehler', message)
        if not data['segments']:
            return messagebox.showinfo('Info', 'Keine Bestellungen notwendig.')
        PreviewWindow(self, data, self.sales_file, self.art_file, self.shops)

    def do_t(self):
        if not self.shops:
            return messagebox.showerror('Fehler', 'Keine Shops gefunden!')
        success, message, data = build_transfer_data(
            self.t_shop.get(), self.t_min.get(), self.t_buf.get(), self.sales_file, self.art_file, self.shops
        )
        if not success:
            return messagebox.showerror('Fehler', message)
        if not data['segments']:
            return messagebox.showinfo('Info', 'Keine Umbuchungen nötig.')
        TransferPreviewWindow(self, data, self.sales_file, self.art_file, self.shops)


if __name__ == '__main__':
    App().mainloop()