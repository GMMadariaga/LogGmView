#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue
import threading
import socket
import configparser
from dataclasses import dataclass
from typing import Tuple, List, Dict
import re
import json
import datetime
import os
import xml.etree.ElementTree as ET
import html
import sys # <-- Importante para la función de ayuda

# --- FUNCIÓN DE AYUDA PARA ENCONTRAR RECURSOS (EL ICONO) ---
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para desarrollo y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
# ----------------------------------------------------------------

@dataclass
class LogEntry:
    timestamp: str
    level: str
    logger: str
    message: str
    raw_data: str = ""

# ... (El resto de las clases NetworkReceiver y ConnectionDialog no cambian) ...
class NetworkReceiver:
    def __init__(self, host: str, port: int, log_queue: queue.Queue, name: str):
        normalized = host.strip().lower() if host else ''
        if normalized in ('', '0.0.0.0', 'localhost', '127.0.0.1'):
            self.host = ''
        else:
            self.host = host.strip()
        self.port = port
        self.log_queue = log_queue
        self.name = name
        self.running = False
        self.socket = None
        self.thread = None
        
    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._receive_logs, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.socket:
            try: self.socket.close()
            except: pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _receive_logs(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.socket.settimeout(0.5)
            self.socket.bind((self.host, self.port))
            while self.running:
                try:
                    data, addr = self.socket.recvfrom(8192)
                    line = data.decode(errors='replace').strip()
                    if line: self._process_log_line(line)
                except socket.timeout: continue
                except OSError:
                    if not self.running: return
        except Exception as e:
            if self.log_queue: self.log_queue.put(('ERROR', f"Error en receptor {self.name}: {e}"))
        finally:
            if self.socket:
                try: self.socket.close()
                except: pass

    def _process_log_line(self, line: str):
        try:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            level = 'INFO'
            logger = 'Default'
            message = line
            if line.startswith('<log4j:event'):
                try:
                    line_no_ns = re.sub(r'log4j:|nlog:', '', line)
                    root = ET.fromstring(line_no_ns)
                    logger = root.get('logger', 'UnknownLogger')
                    level = root.get('level', 'INFO').upper()
                    ts_ms = root.get('timestamp')
                    if ts_ms and ts_ms.isdigit():
                        timestamp = datetime.datetime.fromtimestamp(int(ts_ms) / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    msg_element = root.find('message')
                    message = msg_element.text.strip() if msg_element is not None and msg_element.text else "No message content"
                except ET.ParseError: pass
            elif line.startswith('{'):
                try:
                    data = json.loads(line)
                    timestamp, level, logger, message = data.get('timestamp', timestamp), data.get('level', 'INFO'), data.get('logger', 'Default'), data.get('message', line)
                except json.JSONDecodeError: pass
            else:
                m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (\w+) (.+?) - (.+)', line)
                if m: timestamp, level, logger, message = m.groups()

            entry = LogEntry(timestamp=timestamp, level=level.upper(), logger=logger, message=message, raw_data=line)
            if self.log_queue: self.log_queue.put(('LOG', self.name, entry))
        except Exception: pass

class ConnectionDialog:
    def __init__(self, parent, title: str, name: str = "", host: str = "", port: int = 9999):
        self.result: Tuple[str, str, int] = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.grab_set()
        self.top.geometry("320x180")
        self.top.transient(parent)
        self.top.resizable(False, False)
        self.top.configure(bg="#F0F0F0")

        ttk.Label(self.top, text="Nombre:").grid(row=0, column=0, padx=10, pady=8, sticky='e')
        self.name_entry = ttk.Entry(self.top, width=25); self.name_entry.insert(0, name)
        self.name_entry.grid(row=0, column=1, padx=10, pady=8)

        ttk.Label(self.top, text="Host/IP (vacío=todas):").grid(row=1, column=0, padx=10, pady=8, sticky='e')
        self.host_entry = ttk.Entry(self.top, width=25); self.host_entry.insert(0, host)
        self.host_entry.grid(row=1, column=1, padx=10, pady=8)

        ttk.Label(self.top, text="Puerto:").grid(row=2, column=0, padx=10, pady=8, sticky='e')
        self.port_entry = ttk.Entry(self.top, width=25); self.port_entry.insert(0, str(port))
        self.port_entry.grid(row=2, column=1, padx=10, pady=8)

        btn_frame = ttk.Frame(self.top); btn_frame.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Aceptar", command=self.accept).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Cancelar", command=self.cancel).pack(side='left', padx=10)
        self.name_entry.focus()
        self.top.bind('<Return>', lambda e: self.accept())

    def accept(self):
        try:
            name = self.name_entry.get().strip()
            if not name: raise ValueError("El nombre no puede estar vacío")
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get())
            if not (1 <= port <= 65535): raise ValueError("El puerto debe estar entre 1 y 65535")
            self.result = (name, host, port)
            self.top.destroy()
        except ValueError as e: messagebox.showerror("Error de validación", str(e), parent=self.top)

    def cancel(self): self.top.destroy()

class LogViewerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Network Log Viewer, Ing Guillermo Madariaga")
        self.root.geometry("1400x800")
        
        # --- CAMBIO PARA EL ICONO ---
        try:
            # Usa la función de ayuda para encontrar el icono
            self.root.iconbitmap(resource_path("icon.ico"))
        except tk.TclError:
            print("Icono 'icon.ico' no encontrado. Usando icono por defecto.")
        # --- FIN DEL CAMBIO ---

        self.receivers: Dict[str, NetworkReceiver] = {}
        self.logs: List[Tuple[str, LogEntry]] = []
        self.filtered_logs: List[Tuple[str, LogEntry]] = []
        self.current_receiver_name: str = None
        self.unique_loggers = set()
        self.autoscroll_enabled = tk.BooleanVar(value=True)

        self.level_colors = {'TRACE':'#6c757d','DEBUG':'#007bff','INFO':'#212529','WARN':'#ffc107','ERROR':'#dc3545','FATAL':'#6f42c1'}
        self.level_icons = {'TRACE':'🔹','DEBUG':'⚙️','INFO':'ℹ️','WARN':'⚠️','ERROR':'❗️','FATAL':'💥'}
        self.log_queue = queue.Queue()
        self.status_var = tk.StringVar(value="Listo")
        
        self._setup_styles()
        self.setup_ui()
        self.load_config()
        self.process_queue()

    def _setup_styles(self):
        self.style = ttk.Style(self.root)
        self.root.configure(bg="#f0f0f0")

        BG_COLOR = "#f0f0f0"
        FG_COLOR = "#212529"
        WIDGET_BG = "#ffffff"
        SELECT_BG = "#0078d7"
        SELECT_FG = "#ffffff"
        BORDER_COLOR = "#ced4da"
        BUTTON_BG = "#e9ecef"
        BUTTON_ACTIVE_BG = "#dee2e6"

        self.style.theme_create("lightlog", parent="clam", settings={
            "TFrame": {"configure": {"background": BG_COLOR}},
            "TLabel": {"configure": {"background": BG_COLOR, "foreground": FG_COLOR}},
            "TButton": {"configure": {"background": BUTTON_BG, "foreground": FG_COLOR, "borderwidth": 1, "relief": "solid", "padding": 5, "bordercolor": BORDER_COLOR},
                        "map": {"background": [("active", BUTTON_ACTIVE_BG)]}},
            "TCombobox": {"configure": {"selectbackground": SELECT_BG, "fieldbackground": WIDGET_BG, "background": WIDGET_BG, "foreground": FG_COLOR, "arrowcolor": FG_COLOR},
                          "map": {"foreground": [('readonly', FG_COLOR)]}},
            "TEntry": {"configure": {"selectbackground": SELECT_BG, "fieldbackground": WIDGET_BG, "foreground": FG_COLOR, "insertbackground": FG_COLOR}},
            "Treeview": {"configure": {"background": WIDGET_BG, "fieldbackground": WIDGET_BG, "foreground": FG_COLOR, "relief": "solid"},
                         "map": {"background": [('selected', SELECT_BG)], "foreground": [('selected', SELECT_FG)]}},
            "Treeview.Heading": {"configure": {"background": BUTTON_BG, "foreground": FG_COLOR, "relief": "solid", "font": ('Arial', 10, 'bold'), "borderwidth": 1}},
            "TPanedwindow": {"configure": {"background": BG_COLOR}},
            "TCheckbutton": {"configure": {"background": BG_COLOR, "foreground": FG_COLOR},
                             "map": {"background": [("active", BG_COLOR)], "indicatorcolor": [("selected", SELECT_BG), ("!selected", WIDGET_BG)]}}
        })
        self.style.theme_use("lightlog")
        self.style.configure("Status.TFrame", background=BUTTON_BG, relief='sunken')
        self.root.option_add('*TCombobox*Listbox.background', WIDGET_BG)
        self.root.option_add('*TCombobox*Listbox.foreground', FG_COLOR)
        self.root.option_add('*TCombobox*Listbox.selectBackground', SELECT_BG)
        self.root.option_add('*TCombobox*Listbox.selectForeground', SELECT_FG)
        
    def setup_ui(self):
        toolbar = ttk.Frame(self.root); toolbar.pack(side='top', fill='x', padx=5, pady=5)
        button_texts = {"Nueva Conexión": "➕ Nueva", "Editar": "✏️ Editar", "Eliminar": "🗑️ Eliminar", "Iniciar": "▶️ Iniciar", "Detener": "⏹️ Detener", "Limpiar": "🧹 Limpiar", "Guardar Log": "💾 Guardar", "Test": "🧪 Test"}
        commands = [self.new_connection, self.edit_connection, self.delete_connection, self.start_receiver, self.stop_receiver, self.clear_logs, self.save_logs, self.test_connection]
        
        for (key, text), cmd in zip(button_texts.items(), commands):
            if key in ["Iniciar", "Guardar Log"]: ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=10, pady=2)
            ttk.Button(toolbar, text=text, command=cmd, compound='left').pack(side='left', padx=2)

        main_pane = ttk.PanedWindow(self.root, orient='horizontal'); main_pane.pack(fill='both', expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_pane, width=250); main_pane.add(left_frame, weight=1)
        ttk.Label(left_frame, text="Conexiones:", font=('Arial',10,'bold')).pack(anchor='w', pady=(0,5), padx=2)
        list_frame = ttk.Frame(left_frame); list_frame.pack(fill='both', expand=True)
        self.conn_listbox = tk.Listbox(list_frame, exportselection=False, bg="#FFFFFF", fg="#212529", selectbackground="#0078d7", selectforeground="#FFFFFF", relief="solid", borderwidth=1, highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient='vertical', command=self.conn_listbox.yview); sb.pack(side='right', fill='y')
        self.conn_listbox.configure(yscrollcommand=sb.set); self.conn_listbox.pack(side='left', fill='both', expand=True)
        self.conn_listbox.bind('<<ListboxSelect>>', self.on_connection_select)

        right_frame = ttk.Frame(main_pane); main_pane.add(right_frame, weight=5)
        filter_frame = ttk.Frame(right_frame); filter_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0,5))
        ttk.Label(filter_frame, text="Nivel:").pack(side='left', padx=(0,5))
        self.level_filter = ttk.Combobox(filter_frame, values=['TODOS']+list(self.level_colors.keys()), width=10, state="readonly"); self.level_filter.set('TODOS'); self.level_filter.pack(side='left', padx=5)
        self.level_filter.bind('<<ComboboxSelected>>', self.apply_filters)
        ttk.Label(filter_frame, text="Logger:").pack(side='left', padx=5)
        self.logger_filter = ttk.Combobox(filter_frame, values=['TODOS'], width=35, state="readonly"); self.logger_filter.set('TODOS'); self.logger_filter.pack(side='left', padx=5)
        self.logger_filter.bind('<<ComboboxSelected>>', self.apply_filters)
        ttk.Label(filter_frame, text="Texto:").pack(side='left', padx=5)
        self.text_filter = ttk.Entry(filter_frame); self.text_filter.pack(side='left', fill='x', expand=True, padx=5)
        self.text_filter.bind('<KeyRelease>', self.apply_filters)
        self.autoscroll_check = ttk.Checkbutton(filter_frame, text="Seguimiento Automático", variable=self.autoscroll_enabled, command=self.toggle_autoscroll); self.autoscroll_check.pack(side='right', padx=5)
        self.log_count_var = tk.StringVar(value="0 logs"); ttk.Label(filter_frame, textvariable=self.log_count_var).pack(side='right', padx=5)

        cols = ('Fecha/Hora','Nivel','Logger','Mensaje')
        self.log_tree = ttk.Treeview(right_frame, columns=cols, show='headings')
        self.log_tree.column('Fecha/Hora', width=140, anchor='w', stretch=False)
        self.log_tree.column('Nivel', width=90, anchor='w', stretch=False)
        self.log_tree.column('Logger', width=220, anchor='w', stretch=False)
        self.log_tree.column('Mensaje', width=800, anchor='w', stretch=True)
        for c in cols: self.log_tree.heading(c, text=c)
        vsb = ttk.Scrollbar(right_frame, orient='vertical', command=self.log_tree.yview); hsb = ttk.Scrollbar(right_frame, orient='horizontal', command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.log_tree.grid(row=1, column=0, sticky='nsew'); vsb.grid(row=1, column=1, sticky='ns'); hsb.grid(row=2, column=0, sticky='ew')
        right_frame.grid_rowconfigure(1, weight=1); right_frame.grid_columnconfigure(0, weight=1)
        for lvl,col in self.level_colors.items(): self.log_tree.tag_configure(lvl, foreground=col)
        
        self._create_context_menu()
        self.log_tree.bind('<Button-1>', self.on_log_select)
        self.log_tree.bind('<Button-3>', self._show_context_menu)

        status_bar = ttk.Frame(self.root, style="Status.TFrame"); status_bar.pack(side='bottom', fill='x', ipady=2)
        ttk.Label(status_bar, textvariable=self.status_var, background=self.style.lookup("Status.TFrame", "background")).pack(anchor='w', padx=5)
        
    def _create_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copiar Mensaje", command=self._copy_message)
        self.context_menu.add_command(label="Copiar Línea Completa", command=self._copy_full_line)

    def _show_context_menu(self, event):
        item_id = self.log_tree.identify_row(event.y)
        if item_id:
            if item_id not in self.log_tree.selection():
                self.log_tree.selection_set(item_id)
                self.log_tree.focus(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _copy_message(self):
        if self.log_tree.selection():
            selected_item = self.log_tree.selection()[0]
            message = self.log_tree.item(selected_item, 'values')[3]
            self.root.clipboard_clear(); self.root.clipboard_append(message)
            self.status_var.set("Mensaje copiado al portapapeles.")

    def _copy_full_line(self):
        if self.log_tree.selection():
            selected_item = self.log_tree.selection()[0]
            values = self.log_tree.item(selected_item, 'values')
            full_line = f"[{values[0]}] {values[1]} {values[2]} - {values[3]}"
            self.root.clipboard_clear(); self.root.clipboard_append(full_line)
            self.status_var.set("Línea completa copiada al portapapeles.")

    def on_log_select(self, event):
        if self.log_tree.identify_row(event.y): self.autoscroll_enabled.set(False)

    def toggle_autoscroll(self):
        if self.autoscroll_enabled.get():
            self.log_tree.yview_moveto(1.0)
            self.status_var.set("Seguimiento automático activado.")
        else: self.status_var.set("Seguimiento automático desactivado.")

    def new_connection(self):
        dlg = ConnectionDialog(self.root, "Nueva Conexión")
        self.root.wait_window(dlg.top)
        if dlg.result:
            name, host, port = dlg.result
            if name in self.receivers: messagebox.showerror("Error","Ya existe una conexión con ese nombre."); return
            self.receivers[name] = NetworkReceiver(host, port, self.log_queue, name)
            self.update_connection_list(); self.save_config()
            self.status_var.set(f"Conexión '{name}' creada.")

    def edit_connection(self):
        sel = self.conn_listbox.curselection()
        if not sel: messagebox.showwarning("Advertencia","Seleccione una conexión para editar."); return
        name = self.conn_listbox.get(sel[0]).split(' ')[0]
        rc = self.receivers.get(name)
        if not rc: return
        if rc.running: messagebox.showwarning("Advertencia","Detenga la conexión antes de editarla."); return
        dlg = ConnectionDialog(self.root,"Editar Conexión",name,rc.host,rc.port)
        self.root.wait_window(dlg.top)
        if dlg.result:
            new_name, host, port = dlg.result
            if new_name != name and new_name in self.receivers: messagebox.showerror("Error","Ya existe una conexión con el nuevo nombre."); return
            del self.receivers[name]
            self.receivers[new_name] = NetworkReceiver(host,port,self.log_queue,new_name)
            self.update_connection_list(); self.save_config()
            self.status_var.set(f"Conexión '{new_name}' actualizada.")

    def delete_connection(self):
        sel = self.conn_listbox.curselection()
        if not sel: messagebox.showwarning("Advertencia","Seleccione una conexión para eliminar."); return
        name = self.conn_listbox.get(sel[0]).split(' ')[0]
        rc = self.receivers.get(name)
        if not rc: return
        if rc.running: messagebox.showwarning("Advertencia","Detenga la conexión antes de eliminarla."); return
        if messagebox.askyesno("Confirmar",f"¿Está seguro de que desea eliminar la conexión '{name}'?"):
            del self.receivers[name]
            self.update_connection_list(); self.save_config()
            self.status_var.set(f"Conexión '{name}' eliminada.")

    def start_receiver(self):
        sel = self.conn_listbox.curselection()
        if not sel: messagebox.showwarning("Advertencia","Seleccione una conexión para iniciar."); return
        name = self.conn_listbox.get(sel[0]).split(' ')[0]
        rc = self.receivers.get(name)
        if not rc or rc.running: return
        try:
            rc.start()
            self.update_connection_list()
            self.status_var.set(f"Iniciando '{name}' en {rc.host or '0.0.0.0'}:{rc.port}")
        except Exception as e: messagebox.showerror("Error",f"No se pudo iniciar el receptor: {e}")

    def stop_receiver(self):
        sel = self.conn_listbox.curselection()
        if not sel: messagebox.showwarning("Advertencia","Seleccione una conexión para detener."); return
        name = self.conn_listbox.get(sel[0]).split(' ')[0]
        rc = self.receivers.get(name)
        if not rc or not rc.running: return
        rc.stop()
        self.update_connection_list()
        self.status_var.set(f"Receptor '{name}' detenido.")

    def clear_logs(self):
        if messagebox.askyesno("Confirmar","¿Limpiar todos los logs mostrados?"):
            self.logs.clear(); self.unique_loggers.clear()
            self.update_logger_filter_options(); self.apply_filters()
            self.status_var.set("Logs limpiados.")

    def test_connection(self):
        sel = self.conn_listbox.curselection()
        if not sel: messagebox.showwarning("Advertencia","Seleccione una conexión activa para probar."); return
        name = self.conn_listbox.get(sel[0]).split(' ')[0]
        rc = self.receivers.get(name)
        if not rc or not rc.running: messagebox.showwarning("Advertencia","La conexión debe estar iniciada para enviar un test."); return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                msg = {"timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], "level":"INFO","logger":"TestClient", "message":"Mensaje de prueba desde Network Log Viewer"}
                target_host = '127.0.0.1' if not rc.host or rc.host == '0.0.0.0' else rc.host
                sock.sendto(json.dumps(msg).encode('utf-8'), (target_host, rc.port))
                self.status_var.set(f"Mensaje de prueba enviado a {name}.")
        except Exception as e: messagebox.showerror("Error de prueba",f"No se pudo enviar el mensaje: {e}")

    def _generate_html_report(self, logs_to_save):
        html_head = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><title>Log Export</title><style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f8f9fa; color: #212529; margin: 0; padding: 20px; }
            h1 { color: #343a40; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            th, td { padding: 12px 15px; border: 1px solid #dee2e6; text-align: left; vertical-align: top; }
            th { background-color: #e9ecef; font-weight: 600; }
            td pre { margin: 0; white-space: pre-wrap; word-break: break-all; font-family: "Consolas", "Monaco", "Lucida Console", monospace; }
            .level-cell { font-weight: bold; }"""
        style_rules = [f".level-{level.lower()} .level-cell {{ color: {color}; }}" for level, color in self.level_colors.items()]
        html_body_start = f"""</style></head><body><h1>Log Export - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</h1>
            <table><thead><tr><th>Conexión</th><th>Fecha/Hora</th><th>Nivel</th><th>Logger</th><th>Mensaje</th></tr></thead><tbody>"""
        html_rows = [f"""<tr class="level-{entry.level.lower()}">
            <td>{html.escape(name)}</td><td>{html.escape(entry.timestamp)}</td>
            <td class="level-cell">{self.level_icons.get(entry.level, '')} {html.escape(entry.level)}</td><td>{html.escape(entry.logger)}</td>
            <td><pre>{html.escape(entry.message)}</pre></td></tr>""" for name, entry in logs_to_save]
        html_foot = "</tbody></table></body></html>"
        return html_head + "\n".join(style_rules) + html_body_start + "".join(html_rows) + html_foot

    def save_logs(self):
        logs_to_save = self.filtered_logs if self.filtered_logs else self.logs
        if not logs_to_save: messagebox.showinfo("Aviso","No hay logs para guardar."); return
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("Archivos HTML", "*.html"),("Archivos de Texto", "*.txt"),("Archivos JSON", "*.json"),("Todos los archivos", "*.*")], title="Guardar Log Como")
        if not path: return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                if path.endswith('.json'):
                    json_logs = [{'connection': n, 'timestamp': e.timestamp, 'level': e.level, 'logger': e.logger, 'message': e.message, 'raw_data': e.raw_data} for n, e in logs_to_save]
                    json.dump(json_logs, f, indent=2, ensure_ascii=False)
                elif path.endswith('.html'): f.write(self._generate_html_report(logs_to_save))
                else:
                    for name, entry in logs_to_save: f.write(f"[{name}] [{entry.timestamp}] {entry.level} {entry.logger} - {entry.message}\n")
            self.status_var.set(f"{len(logs_to_save)} logs guardados en {os.path.basename(path)}")
        except Exception as e: messagebox.showerror("Error al Guardar",f"No se pudo guardar el archivo:\n{e}")

    def process_queue(self):
        updated, new_loggers_added = False, False
        try:
            while not self.log_queue.empty():
                item = self.log_queue.get_nowait()
                if item[0]=='ERROR': self.status_var.set(item[1])
                elif item[0]=='LOG':
                    _, name, entry = item
                    self.logs.append((name, entry))
                    if entry.logger not in self.unique_loggers: self.unique_loggers.add(entry.logger); new_loggers_added = True
                    updated = True
        except queue.Empty: pass
        if new_loggers_added: self.update_logger_filter_options()
        if updated: self.apply_filters()
        self.update_connection_list_status()
        self.root.after(100, self.process_queue)

    def update_logger_filter_options(self):
        current_selection = self.logger_filter.get()
        loggers = sorted(list(self.unique_loggers))
        self.logger_filter['values'] = ['TODOS'] + loggers
        if current_selection in self.logger_filter['values']: self.logger_filter.set(current_selection)
        else: self.logger_filter.set('TODOS')

    def apply_filters(self, _=None):
        level_filter, logger_filter, text_filter = self.level_filter.get(), self.logger_filter.get(), self.text_filter.get().lower()
        source_logs = self.logs
        if self.current_receiver_name: source_logs = [log for log in self.logs if log[0] == self.current_receiver_name]
        self.filtered_logs = []
        for name, entry in source_logs:
            if level_filter != 'TODOS' and entry.level != level_filter: continue
            if logger_filter != 'TODOS' and entry.logger != logger_filter: continue
            if text_filter and not (text_filter in entry.message.lower() or text_filter in entry.logger.lower()): continue
            self.filtered_logs.append((name, entry))
        self.update_log_display()
        self.log_count_var.set(f"{len(self.filtered_logs)}/{len(source_logs)} logs")

    def on_connection_select(self, _=None):
        sel = self.conn_listbox.curselection()
        self.current_receiver_name = self.conn_listbox.get(sel[0]).split(' ')[0] if sel else None
        self.apply_filters()

    def update_connection_list(self):
        selected_index = self.conn_listbox.curselection()
        self.conn_listbox.delete(0,'end')
        for name, rc in sorted(self.receivers.items()):
            self.conn_listbox.insert('end',f"{name} - {'ACTIVO' if rc.running else 'INACTIVO'} ({rc.host or '0.0.0.0'}:{rc.port})")
        if selected_index:
            try: self.conn_listbox.selection_set(selected_index[0])
            except IndexError: pass
        self.update_connection_list_status()

    def update_connection_list_status(self):
        for i in range(self.conn_listbox.size()):
            line = self.conn_listbox.get(i)
            name = line.split(' ')[0]
            rc = self.receivers.get(name)
            if rc:
                status_text = "ACTIVO" if rc.running else "INACTIVO"
                color = '#28a745' if rc.running else '#6c757d'
                current_text = line.split(' - ')[1].split(' ')[0]
                if status_text != current_text:
                    self.conn_listbox.delete(i)
                    self.conn_listbox.insert(i, f"{name} - {status_text} ({rc.host or '0.0.0.0'}:{rc.port})")
                self.conn_listbox.itemconfig(i, {'fg': color})

    def load_config(self):
        config_file = "log_viewer_config.ini"
        if not os.path.exists(config_file): return
        try:
            parser = configparser.ConfigParser(); parser.read(config_file, encoding='utf-8')
            for section in parser.sections():
                self.receivers[section] = NetworkReceiver(parser[section].get('host',''), int(parser[section].get('port','9999')), self.log_queue, section)
            self.update_connection_list()
            self.status_var.set(f"Configuración cargada: {len(self.receivers)} conexiones.")
        except Exception as e: self.status_var.set(f"Error al cargar configuración: {e}")

    def save_config(self):
        try:
            parser = configparser.ConfigParser()
            for name, rc in self.receivers.items(): parser[name] = {'host': rc.host, 'port': str(rc.port)}
            with open("log_viewer_config.ini",'w',encoding='utf-8') as f: parser.write(f)
        except Exception as e: self.status_var.set(f"Error al guardar configuración: {e}")

    def update_log_display(self):
        selected_id = self.log_tree.selection()[0] if self.log_tree.selection() else None
        self.log_tree.delete(*self.log_tree.get_children())
        new_selected_id = None
        for i, (_, entry) in enumerate(self.filtered_logs[-1000:]):
            icon = self.level_icons.get(entry.level, '▪️')
            values = (entry.timestamp, f"{icon} {entry.level}", entry.logger, entry.message)
            item_id = self.log_tree.insert('', 'end', iid=f"log_{i}", values=values, tags=(entry.level,))
            if selected_id == item_id:
                new_selected_id = item_id

        if self.autoscroll_enabled.get() and self.filtered_logs:
            self.log_tree.yview_moveto(1.0)
        elif new_selected_id:
            self.log_tree.selection_set(new_selected_id)
            self.log_tree.focus(new_selected_id)

def main():
    root = tk.Tk()
    app = LogViewerApp(root)
    def on_close():
        for rc in app.receivers.values():
            if rc.running: rc.stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__=="__main__":
    main()