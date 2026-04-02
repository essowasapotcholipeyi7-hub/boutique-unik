# database.py
import sqlite3
from datetime import datetime, timezone
from config import Config

def get_db():
    """Établit la connexion à la base de données"""
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crée les tables si elles n'existent pas"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Table PRODUITS (catalogue)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            nom TEXT NOT NULL,
            categorie TEXT,
            prix_achat REAL DEFAULT 0,
            prix_vente REAL DEFAULT 0,
            fournisseur TEXT,
            actif INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    
    # Table STOCK
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produit_id INTEGER,
            produit_nom TEXT,
            stock_initial INTEGER DEFAULT 0,
            entrees INTEGER DEFAULT 0,
            sorties INTEGER DEFAULT 0,
            stock_restant INTEGER DEFAULT 0,
            seuil_alerte INTEGER DEFAULT 10,
            prix_achat REAL DEFAULT 0,
            prix_vente REAL DEFAULT 0,
            categorie TEXT,
            fournisseur TEXT,
            FOREIGN KEY (produit_id) REFERENCES produits(id)
        )
    ''')
    
    # Table VENTES
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vente_id TEXT UNIQUE,
            date TEXT,
            heure TEXT,
            produit TEXT,
            quantite INTEGER,
            prix_unitaire REAL,
            prix_vendu REAL,
            difference REAL,
            sous_total REAL,
            remise REAL,
            total_net REAL,
            vendeur TEXT,
            statut TEXT DEFAULT 'VALIDÉE',
            created_at TEXT
        )
    ''')
    
    # Table JOURNAL_MVM
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS journal_mvm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            heure TEXT,
            type TEXT,
            produit TEXT,
            quantite TEXT,
            stock_avant INTEGER,
            stock_apres INTEGER,
            utilisateur TEXT,
            details TEXT,
            created_at TEXT
        )
    ''')
    
    # Table UTILISATEURS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            nom TEXT,
            role TEXT DEFAULT 'vendeur',
            actif INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    
    conn.commit()
    
    # Ajouter les vendeurs par défaut
    from config import Config
    for username, data in Config.VENDEURS.items():
        cursor.execute('SELECT * FROM utilisateurs WHERE username = ?', (username,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO utilisateurs (username, password, nom, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, data['mdp'], data['nom'], 'vendeur', datetime.now(timezone.utc).isoformat()))
    
    # Ajouter produits de test si nécessaire
    cursor.execute('SELECT COUNT(*) FROM produits')
    if cursor.fetchone()[0] == 0:
        produits_test = [
            ('PROD_001', 'BICS', 'Fournitures', 100, 250, 'Fournisseur X'),
            ('PROD_002', 'PAGNES', 'Tissus', 1500, 2500, 'Fournisseur Y'),
            ('PROD_003', 'VIN ROUGE', 'Boissons', 2000, 3500, 'Fournisseur Z'),
        ]
        for prod in produits_test:
            cursor.execute('''
                INSERT INTO produits (code, nom, categorie, prix_achat, prix_vente, fournisseur, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (prod[0], prod[1], prod[2], prod[3], prod[4], prod[5], datetime.now(timezone.utc).isoformat()))
            
            cursor.execute('''
                INSERT INTO stock (produit_id, produit_nom, stock_initial, stock_restant, seuil_alerte, prix_achat, prix_vente, categorie, fournisseur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cursor.lastrowid, prod[1], 100, 100, 10, prod[3], prod[4], prod[2], prod[5]))
    
    conn.commit()
    conn.close()
    print("✅ Base de données initialisée")

def get_current_datetime():
    """Retourne la date et l'heure actuelles au format GMT (Togo)"""
    now = datetime.now(timezone.utc)
    return {
        'date': now.strftime('%d/%m/%Y'),
        'time': now.strftime('%H:%M:%S'),
        'datetime': now.strftime('%d/%m/%Y %H:%M:%S')
    }