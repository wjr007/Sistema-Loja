import sqlite3
import os
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from kivy.core.window import Window

# Configurações de Cores
VERDE_ESCURO = "#1B5E20"
VERDE_MEDIO = "#2E7D32"
VERMELHO_ERRO = "#C62828"
AMARELO = "#FBC02D"
FUNDO = "#121212"

class BancoDados:
    def __init__(self):
        self.db_name = "sistema_cacador.db"
        self.criar_tabelas()

    def conectar(self):
        return sqlite3.connect(self.db_name)

    def criar_tabelas(self):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS produtos (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT NOT NULL,
                            descricao TEXT,
                            preco REAL NOT NULL,
                            quantidade INTEGER DEFAULT 0)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS vendas (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            data_hora TEXT,
                            valor_total REAL,
                            forma_pagamento TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS itens_venda (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            venda_id INTEGER,
                            produto_id INTEGER,
                            quantidade INTEGER,
                            preco_unitario REAL,
                            subtotal REAL,
                            FOREIGN KEY(venda_id) REFERENCES vendas(id))''')
        conn.commit()
        conn.close()

    def obter_estatisticas(self):
        conn = self.conectar()
        cursor = conn.cursor()
        data_hoje = datetime.now().strftime("%d/%m/%Y")
        data_mes = datetime.now().strftime("/%m/%Y")
        cursor.execute("SELECT SUM(valor_total) FROM vendas WHERE data_hora LIKE ?", (data_hoje + "%",))
        hoje = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT SUM(valor_total) FROM vendas WHERE data_hora LIKE ?", ("%" + data_mes + "%",))
        mes = cursor.fetchone()[0] or 0.0
        cursor.execute('''SELECT p.nome, SUM(i.quantidade) as total_qtd 
                          FROM itens_venda i 
                          JOIN produtos p ON i.produto_id = p.id 
                          GROUP BY p.nome 
                          ORDER BY total_qtd DESC LIMIT 5''')
        ranking = cursor.fetchall()
        conn.close()
        return hoje, mes, ranking

    def adicionar_produto(self, nome, descricao, preco, quantidade):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO produtos (nome, descricao, preco, quantidade) VALUES (?, ?, ?, ?)",
                       (nome, descricao, preco, quantidade))
        conn.commit()
        conn.close()

    def acrescentar_estoque(self, produto_id, qtd_nova):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("UPDATE produtos SET quantidade = quantidade + ? WHERE id = ?", (qtd_nova, produto_id))
        conn.commit()
        conn.close()

    def obter_produtos(self):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM produtos")
        produtos = cursor.fetchall()
        conn.close()
        return produtos

    def registrar_venda(self, lista_itens, total, forma_pagamento):
        conn = self.conectar()
        cursor = conn.cursor()
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cursor.execute("INSERT INTO vendas (data_hora, valor_total, forma_pagamento) VALUES (?, ?, ?)",
                       (data_atual, total, forma_pagamento))
        venda_id = cursor.lastrowid
        for item in lista_itens:
            cursor.execute("INSERT INTO itens_venda (venda_id, produto_id, quantidade, preco_unitario, subtotal) VALUES (?, ?, ?, ?, ?)",
                           (venda_id, item[0], item[3], item[2], item[2]*item[3]))
            cursor.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE id = ?", (item[3], item[0]))
        conn.commit()
        conn.close()
        return True

class TelaVendas(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(10)
        self.spacing = dp(10)
        self.carrinho = {}
        self.total = 0.0
        self.db = App.get_running_app().banco_dados
        self.add_widget(Label(text="Use [+] para adicionar e [-] para remover", size_hint_y=None, height=dp(30), color=get_color_from_hex(AMARELO)))
        self.scroll = ScrollView()
        self.grid_produtos = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        self.grid_produtos.bind(minimum_height=self.grid_produtos.setter('height'))
        self.scroll.add_widget(self.grid_produtos)
        self.add_widget(self.scroll)
        self.resumo_container = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(210), padding=dp(10), spacing=dp(5))
        with self.resumo_container.canvas.before:
            Color(0.15, 0.15, 0.15, 1)
            self.rect_resumo = Rectangle(pos=self.resumo_container.pos, size=self.resumo_container.size)
        self.resumo_container.bind(pos=self.atualizar_rect_resumo, size=self.atualizar_rect_resumo)
        self.lbl_itens = Label(text="Carrinho vazio", halign='left', text_size=(dp(350), None), font_size=dp(13))
        self.lbl_total = Label(text="TOTAL: R$ 0,00", font_size=dp(22), bold=True, color=get_color_from_hex(AMARELO))
        acoes_layout = BoxLayout(spacing=dp(5), size_hint_y=None, height=dp(45))
        self.pagamento = Spinner(text="Forma de Pagamento", values=("Dinheiro", "PIX", "Débito", "Crédito"))
        btn_limpar = Button(text="Limpar", size_hint_x=None, width=dp(80), background_color=get_color_from_hex(VERMELHO_ERRO))
        btn_limpar.bind(on_press=self.limpar_total)
        acoes_layout.add_widget(self.pagamento); acoes_layout.add_widget(btn_limpar)
        btn_finalizar = Button(text="FINALIZAR VENDA", background_color=get_color_from_hex(VERDE_MEDIO), bold=True, size_hint_y=None, height=dp(50))
        btn_finalizar.bind(on_press=self.finalizar_venda)
        self.resumo_container.add_widget(self.lbl_itens); self.resumo_container.add_widget(self.lbl_total)
        self.resumo_container.add_widget(acoes_layout); self.resumo_container.add_widget(btn_finalizar)
        self.add_widget(self.resumo_container)
        self.carregar_produtos()

    def atualizar_rect_resumo(self, instance, value):
        self.rect_resumo.pos = instance.pos
        self.rect_resumo.size = instance.size

    def carregar_produtos(self):
        self.grid_produtos.clear_widgets()
        for p in self.db.obter_produtos():
            item_box = BoxLayout(size_hint_y=None, height=dp(70), padding=dp(5), spacing=dp(10))
            with item_box.canvas.before:
                Color(0.2, 0.2, 0.2, 1)
                Rectangle(pos=item_box.pos, size=item_box.size)
            info = Label(text=f"{p[1]}\nR$ {p[3]:.2f} (Estoque: {p[4]})", halign='left', text_size=(dp(180), None))
            btns_box = BoxLayout(size_hint_x=None, width=dp(130), spacing=dp(5))
            btn_sub = Button(text="-", background_color=get_color_from_hex(VERMELHO_ERRO), font_size=dp(24), bold=True)
            btn_sub.bind(on_press=lambda x, prod=p: self.remover_do_carrinho(prod))
            btn_add = Button(text="+", background_color=get_color_from_hex(VERDE_MEDIO), font_size=dp(24), bold=True)
            btn_add.bind(on_press=lambda x, prod=p: self.adicionar_ao_carrinho(prod))
            btns_box.add_widget(btn_sub); btns_box.add_widget(btn_add)
            item_box.add_widget(info); item_box.add_widget(btns_box)
            self.grid_produtos.add_widget(item_box)

    def adicionar_ao_carrinho(self, produto):
        p_id = produto[0]
        if p_id in self.carrinho: self.carrinho[p_id]['qtd'] += 1
        else: self.carrinho[p_id] = {'nome': produto[1], 'preco': produto[3], 'qtd': 1}
        self.total += produto[3]
        self.atualizar_interface_carrinho()

    def remover_do_carrinho(self, produto):
        p_id = produto[0]
        if p_id in self.carrinho:
            if self.carrinho[p_id]['qtd'] > 0:
                self.carrinho[p_id]['qtd'] -= 1
                self.total -= produto[3]
                if self.carrinho[p_id]['qtd'] == 0: del self.carrinho[p_id]
                self.atualizar_interface_carrinho()

    def limpar_total(self, instance):
        self.carrinho = {}; self.total = 0.0
        self.atualizar_interface_carrinho()

    def atualizar_interface_carrinho(self):
        if self.total < 0: self.total = 0.0
        texto = [f"{info['qtd']}x {info['nome']}" for info in self.carrinho.values()]
        self.lbl_itens.text = ", ".join(texto) if texto else "Carrinho vazio"
        self.lbl_total.text = f"TOTAL: R$ {self.total:.2f}"

    def finalizar_venda(self, instance):
        if not self.carrinho or self.pagamento.text == "Forma de Pagamento":
            Popup(title="Aviso", content=Label(text="Carrinho vazio ou\nsem forma de pagamento!"), size_hint=(0.7,0.3)).open()
            return
        lista_final = [(p_id, info['nome'], info['preco'], info['qtd']) for p_id, info in self.carrinho.items()]
        if self.db.registrar_venda(lista_final, self.total, self.pagamento.text):
            self.limpar_total(None)
            self.pagamento.text = "Forma de Pagamento"; self.carregar_produtos() 
            App.get_running_app().atualizar_dados_globais()

class TelaDashboard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'; self.padding = dp(15); self.spacing = dp(15)
        self.db = App.get_running_app().banco_dados
        self.add_widget(Label(text="DASHBOARD DE VENDAS", font_size=dp(18), bold=True, color=get_color_from_hex(AMARELO), size_hint_y=None, height=dp(40)))
        cards = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(100))
        self.card_hoje = self.criar_card("HOJE", "R$ 0,00", VERDE_MEDIO)
        self.card_mes = self.criar_card("MÊS", "R$ 0,00", "#1976D2")
        cards.add_widget(self.card_hoje); cards.add_widget(self.card_mes)
        self.add_widget(cards); self.add_widget(Label(text="TOP 5 PRODUTOS", bold=True, size_hint_y=None, height=dp(30)))
        self.lista_ranking = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.lista_ranking.bind(minimum_height=self.lista_ranking.setter('height'))
        scroll = ScrollView(); scroll.add_widget(self.lista_ranking); self.add_widget(scroll)
        btn_refresh = Button(text="ATUALIZAR", size_hint_y=None, height=dp(50), background_color=get_color_from_hex(AMARELO), color=(0,0,0,1))
        btn_refresh.bind(on_press=self.atualizar_dados); self.add_widget(btn_refresh); self.atualizar_dados()

    def criar_card(self, titulo, valor, cor):
        box = BoxLayout(orientation='vertical', padding=dp(10))
        with box.canvas.before:
            Color(*get_color_from_hex(cor)[:3]); box.rect = Rectangle(pos=box.pos, size=box.size)
        box.bind(pos=self.update_rect, size=self.update_rect)
        box.add_widget(Label(text=titulo, font_size=dp(12), bold=True))
        lbl_valor = Label(text=valor, font_size=dp(18), bold=True); box.lbl_valor = lbl_valor
        box.add_widget(lbl_valor); return box

    def update_rect(self, instance, value):
        instance.rect.pos = instance.pos; instance.rect.size = instance.size

    def atualizar_dados(self, *args):
        hoje, mes, ranking = self.db.obter_estatisticas()
        self.card_hoje.lbl_valor.text = f"R$ {hoje:.2f}"; self.card_mes.lbl_valor.text = f"R$ {mes:.2f}"
        self.lista_ranking.clear_widgets()
        for i, (nome, qtd) in enumerate(ranking, 1):
            self.lista_ranking.add_widget(Label(text=f"{i}º {nome} ({qtd} un)", size_hint_y=None, height=dp(30)))

class TelaEstoque(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'; self.padding = dp(10)
        self.db = App.get_running_app().banco_dados
        self.nome = TextInput(hint_text="Nome", size_hint_y=None, height=dp(40))
        self.preco = TextInput(hint_text="Preço", input_filter='float', size_hint_y=None, height=dp(40))
        self.qtd = TextInput(hint_text="Estoque Inicial", input_filter='int', size_hint_y=None, height=dp(40))
        self.btn_acao = Button(text="Cadastrar Novo Produto", size_hint_y=None, height=dp(45), background_color=get_color_from_hex(VERDE_MEDIO))
        self.btn_acao.bind(on_press=self.salvar_novo)
        self.add_widget(self.nome); self.add_widget(self.preco); self.add_widget(self.qtd); self.add_widget(self.btn_acao)
        self.add_widget(Label(text="LISTA DE ESTOQUE", size_hint_y=None, height=dp(40), bold=True))
        self.lista = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.lista.bind(minimum_height=self.lista.setter('height'))
        sc = ScrollView(); sc.add_widget(self.lista); self.add_widget(sc); self.carregar_lista()

    def salvar_novo(self, instance):
        try:
            n, p, q = self.nome.text, float(self.preco.text or 0), int(self.qtd.text or 0)
            if n: self.db.adicionar_produto(n, "", p, q); self.limpar(); self.carregar_lista(); App.get_running_app().tela_vendas.carregar_produtos()
        except: pass

    def carregar_lista(self):
        self.lista.clear_widgets()
        for p in self.db.obter_produtos():
            box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
            with box.canvas.before: Color(0.2, 0.2, 0.2, 1); Rectangle(pos=box.pos, size=box.size)
            box.add_widget(Label(text=f"{p[1]} (Qtd: {p[4]})", size_hint_x=0.4))
            entrada_qtd = TextInput(hint_text="+", size_hint_x=0.3, multiline=False, input_filter='int')
            btn_add = Button(text="Soma", size_hint_x=0.3, background_color=get_color_from_hex(VERDE_ESCURO))
            btn_add.bind(on_press=lambda x, pid=p[0], inp=entrada_qtd: self.processar_soma(pid, inp))
            box.add_widget(entrada_qtd); box.add_widget(btn_add); self.lista.add_widget(box)

    def processar_soma(self, pid, input_widget):
        try:
            valor = int(input_widget.text or 0)
            if valor > 0: self.db.acrescentar_estoque(pid, valor); self.carregar_lista(); App.get_running_app().tela_vendas.carregar_produtos()
        except: pass

    def limpar(self): self.nome.text = ""; self.preco.text = ""; self.qtd.text = ""

class TelaHistorico(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'; self.padding = dp(10)
        self.db = App.get_running_app().banco_dados
        self.lbl_total = Label(text="Total: R$ 0,00", bold=True, size_hint_y=None, height=dp(30))
        self.filtro = Spinner(text="Todos", values=("Todos", "Dinheiro", "PIX", "Débito", "Crédito"), size_hint_y=None, height=dp(40))
        self.filtro.bind(text=self.atualizar); self.add_widget(self.lbl_total); self.add_widget(self.filtro)
        self.lista = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.lista.bind(minimum_height=self.lista.setter('height'))
        sc = ScrollView(); sc.add_widget(self.lista); self.add_widget(sc); self.atualizar()

    def atualizar(self, *args):
        self.lista.clear_widgets(); f = self.filtro.text; conn = self.db.conectar(); cursor = conn.cursor()
        query = "SELECT * FROM vendas" + (f" WHERE forma_pagamento='{f}'" if f != "Todos" else "") + " ORDER BY id DESC"
        cursor.execute(query); vendas = cursor.fetchall(); total = 0
        for v in vendas:
            total += v[2]
            box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(60), padding=dp(5))
            box.add_widget(Label(text=f"{v[1]} - R$ {v[2]:.2f}", bold=True))
            box.add_widget(Label(text=f"Pagamento: {v[3]}", font_size=dp(11))); self.lista.add_widget(box)
        self.lbl_total.text = f"Total Filtrado: R$ {total:.2f}"; conn.close()

class CaixaCacadorApp(App):
    def build(self):
        self.icon = 'logo.png' # Favicon
        self.banco_dados = BancoDados()
        Window.clearcolor = get_color_from_hex(FUNDO)
        layout_principal = BoxLayout(orientation='vertical')
        
        # CABEÇALHO AUMENTADO PARA A LOGO FICAR GRANDE
        header = BoxLayout(size_hint_y=None, height=dp(120), padding=dp(10), spacing=dp(15))
        with header.canvas.before:
            Color(*get_color_from_hex(VERDE_ESCURO)[:3])
            self.rect_head = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self.update_head, size=self.update_head)
        
        # LOGO AUMENTADA (width=dp(100))
        header.add_widget(Image(source='logo.png', size_hint=(None, 1), width=dp(100)))
        header.add_widget(Label(text="CAÇADOR GESTÃO", font_size=dp(24), bold=True, color=get_color_from_hex(AMARELO)))
        layout_principal.add_widget(header)

        self.tp = TabbedPanel(do_default_tab=False)
        self.tab_v = TabbedPanelItem(text="Vendas"); self.tela_vendas = TelaVendas(); self.tab_v.add_widget(self.tela_vendas)
        self.tab_e = TabbedPanelItem(text="Estoque"); self.tela_estoque = TelaEstoque(); self.tab_e.add_widget(self.tela_estoque)
        self.tab_h = TabbedPanelItem(text="Histórico"); self.tela_historico = TelaHistorico(); self.tab_h.add_widget(self.tela_historico)
        self.tab_d = TabbedPanelItem(text="Dash"); self.tela_dashboard = TelaDashboard(); self.tab_d.add_widget(self.tela_dashboard)
        
        self.tp.add_widget(self.tab_v); self.tp.add_widget(self.tab_e); self.tp.add_widget(self.tab_h); self.tp.add_widget(self.tab_d)
        layout_principal.add_widget(self.tp); return layout_principal

    def update_head(self, inst, val): self.rect_head.pos = inst.pos; self.rect_head.size = inst.size
    def atualizar_dados_globais(self): self.tela_historico.atualizar(); self.tela_dashboard.atualizar_dados(); self.tela_estoque.carregar_lista()

if __name__ == "__main__":
    CaixaCacadorApp().run()