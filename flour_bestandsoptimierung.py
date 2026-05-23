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
def run_orders(mode, min_stock, apply_buffer, sales_file, art_file, shops):
    success, _, art_df, sales_pivot = load_and_prep_data(sales_file, art_file)
    if not success: return False, sales_pivot

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
                if shop in sales_pivot.columns: sales += int(sales_pivot.at[art_no, shop])
        else:
            stock = int(float(row.get(f'Bestand: {mode}', 0))) if pd.notnull(row.get(f'Bestand: {mode}')) else 0
            if mode in sales_pivot.columns: sales = int(sales_pivot.at[art_no, mode])
                
        if stock == 0 and sales == 0: continue
        bedarf = calculate_need(sales, min_stock, apply_buffer)
        to_order = bedarf - stock
        
        if to_order > 0:
            results.append({
                'Lieferant': lieferant, 'Hersteller': hersteller, 
                'Name': art_name, 'Bestellmenge': to_order
            })

    if not results: return True, "Keine Bestellungen notwendig."

    df_out = pd.DataFrame(results).sort_values(by=['Lieferant', 'Hersteller', 'Name'])
    pdf_file = os.path.join(BASE_DIR, f"Bestellung_{sanitize_filename(mode)}.pdf")
    
    try:
        c = canvas.Canvas(pdf_file, pagesize=A4)
        width, height = A4
        margin, form = 40, c.acroForm
        y = height - margin - 50

        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin, height - margin, f"Bestellvorschlag: {mode}")
        
        current_lieferant = None
        for idx, row in df_out.iterrows():
            if y < 70: 
                c.showPage()
                y = height - margin - 20
            
            if row['Lieferant'] != current_lieferant:
                current_lieferant = row['Lieferant']
                y -= 20
                c.setFont("Helvetica-Bold", 12)
                c.drawString(margin, y, f"Lieferant: {current_lieferant}")
                y -= 20
                c.setFont("Helvetica-Bold", 10)
                c.drawString(margin, y, "Hersteller")
                c.drawString(margin + 100, y, "Artikelname")
                c.drawString(margin + 360, y, "Menge")
                c.drawString(margin + 415, y, "Bestellt")
                c.drawString(margin + 470, y, "Toter Art.")
                c.line(margin, y-5, width-margin, y-5)
                y -= 20

            c.setFont("Helvetica", 9)
            c.drawString(margin, y, str(row['Hersteller'])[:18])
            c.drawString(margin + 100, y, str(row['Name'])[:50])
            c.drawString(margin + 360, y, str(row['Bestellmenge']))
            
            form.checkbox(name=f"b_{idx}", x=margin + 425, y=y-2, size=12)
            form.checkbox(name=f"t_{idx}", x=margin + 490, y=y-2, size=12)
            c.setStrokeColor(colors.lightgrey); c.line(margin, y-5, width-margin, y-5); c.setStrokeColor(colors.black)
            y -= 18
            
        c.save()
        return True, f"Erfolg! PDF erstellt:\n{pdf_file}"
    except Exception as e:
        return False, f"Fehler: {e}"

# ==========================================
# LOGIK: LAGERBEWEGUNG
# ==========================================
def run_transfers(source_shop, min_stock, apply_buffer, sales_file, art_file, shops):
    target_shops = [s for s in shops if s != source_shop]
    success, _, art_df, sales_pivot = load_and_prep_data(sales_file, art_file)
    if not success: return False, sales_pivot
        
    results = []
    moved_counts = {ts: 0 for ts in target_shops}
    
    for _, row in art_df.iterrows():
        art_no = str(row.get('Artikel-Nr', '')).strip()
        if not art_no or art_no == 'nan': continue
        stock_source = int(float(row.get(f'Bestand: {source_shop}', 0))) if pd.notnull(row.get(f'Bestand: {source_shop}')) else 0
        sales_source = int(sales_pivot.at[art_no, source_shop]) if not sales_pivot.empty and art_no in sales_pivot.index and source_shop in sales_pivot.columns else 0
        bedarf_source = calculate_need(sales_source, min_stock, apply_buffer)
        surplus = stock_source - bedarf_source
        
        if surplus > 0:
            target_sales = {ts: (int(sales_pivot.at[art_no, ts]) if not sales_pivot.empty and art_no in sales_pivot.index and ts in sales_pivot.columns else 0) for ts in target_shops}
            dist = distribute_surplus(surplus, target_sales)
            
            if sum(dist.values()) > 0:
                hersteller = str(row.get('Hersteller', '')).strip()
                hersteller = hersteller if hersteller and hersteller != 'nan' else "Ohne Hersteller"
                
                row_data = {'Hersteller': hersteller, 'Name': str(row.get('Bezeichnung', ''))}
                for ts in target_shops:
                    row_data[ts] = dist[ts]
                    if dist[ts] > 0: moved_counts[ts] += 1
                results.append(row_data)

    if not results: return True, "Keine Umbuchungen nötig."

    df_out = pd.DataFrame(results).sort_values(by=['Hersteller', 'Name'])
    pdf_file = os.path.join(BASE_DIR, f"Lagerbewegung_{sanitize_filename(source_shop)}.pdf")
    
    try:
        c = canvas.Canvas(pdf_file, pagesize=A4)
        width, height = A4
        margin, form = 40, c.acroForm
        y = height - 80
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin, height - 40, f"Lagerbewegung: Von {source_shop}")

        current_hersteller = None
        for idx, row in df_out.iterrows():
            if y < 70: 
                c.showPage()
                y = height - 50
            
            if row['Hersteller'] != current_hersteller:
                current_hersteller = row['Hersteller']
                y -= 10
                c.setFont("Helvetica-Bold", 11)
                c.drawString(margin, y, f"Hersteller: {current_hersteller}")
                y -= 20
                c.setFont("Helvetica-Bold", 10)
                c.drawString(margin, y, "Artikelname")
                x_offset = margin + 250
                for ts in target_shops:
                    c.drawString(x_offset, y, ts[:10])
                    x_offset += 60
                c.drawString(x_offset, y, "Erledigt")
                c.line(margin, y-5, width-margin, y-5)
                y -= 20

            c.setFont("Helvetica", 9)
            c.drawString(margin, y, str(row['Name'])[:45])
            x_offset = margin + 250
            for ts in target_shops:
                if row[ts] > 0: c.drawString(x_offset + 10, y, str(row[ts]))
                x_offset += 60
            form.checkbox(name=f"done_{idx}", x=x_offset + 10, y=y-2, size=12)
            c.setStrokeColor(colors.lightgrey); c.line(margin, y-5, width-margin, y-5); c.setStrokeColor(colors.black)
            y -= 18

        c.save()
        summary = "".join([f"- {moved_counts[ts]} Art. für {ts}\n" for ts in target_shops])
        return True, f"PDF erstellt:\n{pdf_file}\n\n{summary}"
    except Exception as e:
        return False, f"Fehler: {e}"

# ==========================================
# UI
# ==========================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bestands- & Bestelloptimierung v2.0")
        self.geometry("580x550")
        style = ttk.Style()
        if 'clam' in style.theme_names(): style.theme_use('clam')
        
        self.sales_file = get_latest_file('*articlessold*.csv')
        self.art_file = get_latest_file('*articles_*stammdaten*.csv') or get_latest_file('*articles_*.csv')
        
        # Dynamische Shop-Ermittlung
        self.shops = get_dynamic_shops(self.sales_file)
        
        self.build_ui()

    def build_ui(self):
        header = ttk.Frame(self, padding=20)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Datenquellen:", font=("Sans", 12, "bold")).pack(anchor="w")
        ttk.Label(header, text=f"Verkäufe: {os.path.basename(self.sales_file) if self.sales_file else 'FEHLT'}", foreground="green" if self.sales_file else "red").pack(anchor="w")
        ttk.Label(header, text=f"Stammdaten: {os.path.basename(self.art_file) if self.art_file else 'FEHLT'}", foreground="green" if self.art_file else "red").pack(anchor="w")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.tab_o = ttk.Frame(self.nb, padding=20)
        self.tab_t = ttk.Frame(self.nb, padding=20)
        self.nb.add(self.tab_o, text=" Bestellvorschlag ")
        self.nb.add(self.tab_t, text=" Lagerbewegung ")

        # Falls keine Shops gefunden wurden (Fallback)
        shop_list = self.shops if self.shops else ["Keine Daten"]
        first_shop = shop_list[0] if shop_list else ""

        # Tab: Bestellung
        ttk.Label(self.tab_o, text="Für welches Lager soll bestellt werden?", font=("Sans", 11, "bold")).pack(anchor="w")
        self.o_shop = tk.StringVar(value="Zentrale Bestellung")
        ttk.Combobox(self.tab_o, textvariable=self.o_shop, values=["Zentrale Bestellung"] + shop_list, state="readonly").pack(fill=tk.X, pady=5)
        
        ttk.Label(self.tab_o, text="Mindestbestand:", font=("Sans", 11, "bold")).pack(anchor="w", pady=(10,0))
        self.o_min = tk.IntVar(value=0)
        l_min = ttk.Label(self.tab_o, text="0 Stück")
        ttk.Scale(self.tab_o, from_=0, to=20, variable=self.o_min, command=lambda v: l_min.config(text=f"{int(float(v))} Stück")).pack(fill=tk.X)
        l_min.pack()
        
        self.o_buf = tk.BooleanVar()
        ttk.Checkbutton(self.tab_o, text="Zukunftspuffer: +20% Reserve auf historische Verkäufe", variable=self.o_buf).pack(anchor="w", pady=15)
        ttk.Button(self.tab_o, text="Bestellungen berechnen", command=self.do_o).pack(fill=tk.X, side=tk.BOTTOM)

        # Tab: Lagerbewegung
        ttk.Label(self.tab_t, text="Von wo wird umgebucht?", font=("Sans", 11, "bold")).pack(anchor="w")
        self.t_shop = tk.StringVar(value=first_shop)
        ttk.Combobox(self.tab_t, textvariable=self.t_shop, values=shop_list, state="readonly").pack(fill=tk.X, pady=5)
        
        ttk.Label(self.tab_t, text="Mindestbestand (Bleibt im Shop):", font=("Sans", 11, "bold")).pack(anchor="w", pady=(10,0))
        self.t_min = tk.IntVar(value=0)
        l_tmin = ttk.Label(self.tab_t, text="0 Stück")
        ttk.Scale(self.tab_t, from_=0, to=20, variable=self.t_min, command=lambda v: l_tmin.config(text=f"{int(float(v))} Stück")).pack(fill=tk.X)
        l_tmin.pack()
        
        self.t_buf = tk.BooleanVar()
        ttk.Checkbutton(self.tab_t, text="Zukunftspuffer: +20% Verkaufsreserve behalten", variable=self.t_buf).pack(anchor="w", pady=15)
        ttk.Button(self.tab_t, text="Lagerbewegung berechnen", command=self.do_t).pack(fill=tk.X, side=tk.BOTTOM)

    def do_o(self):
        if not self.shops: return messagebox.showerror("Fehler", "Keine Shops gefunden!")
        s, m = run_orders(self.o_shop.get(), self.o_min.get(), self.o_buf.get(), self.sales_file, self.art_file, self.shops)
        messagebox.showinfo("Info", m) if s else messagebox.showerror("Fehler", m)

    def do_t(self):
        if not self.shops: return messagebox.showerror("Fehler", "Keine Shops gefunden!")
        s, m = run_transfers(self.t_shop.get(), self.t_min.get(), self.t_buf.get(), self.sales_file, self.art_file, self.shops)
        messagebox.showinfo("Info", m) if s else messagebox.showerror("Fehler", m)

if __name__ == "__main__":
    App().mainloop()
